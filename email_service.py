import os
import json
import logging
from datetime import datetime

import resend

from config import ADMIN_EMAIL


def format_date_german(date_str):
    """Konvertiert YYYY-MM-DD zu TT.MM.JJJJ"""
    try:
        if '-' in str(date_str):
            parts = str(date_str).split('-')
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except:
        pass
    return str(date_str)


def get_german_weekday(weekday_abbr):
    """Konvertiert englische Wochentag-Abkürzung zu deutschem Namen"""
    weekday_map = {
        'Mon': 'Montag',
        'Tue': 'Dienstag',
        'Wed': 'Mittwoch',
        'Thu': 'Donnerstag',
        'Fri': 'Freitag',
        'Sat': 'Samstag',
        'Sun': 'Sonntag'
    }
    return weekday_map.get(weekday_abbr, weekday_abbr)


def get_resend_credentials():
    """Holt Resend API-Key - zuerst aus ENV, dann über Replit Connector"""

    env_api_key = os.environ.get('RESEND_API_KEY')
    env_from_email = os.environ.get('RESEND_FROM_EMAIL',
                                    'SportOase <mauro@sportoase.app>')

    if env_api_key:
        print(f"[EMAIL] Resend API-Key aus Environment Variable gefunden")
        return env_api_key, env_from_email

    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')

    x_replit_token = None
    if os.environ.get('REPL_IDENTITY'):
        x_replit_token = 'repl ' + os.environ.get('REPL_IDENTITY')
    elif os.environ.get('WEB_REPL_RENEWAL'):
        x_replit_token = 'depl ' + os.environ.get('WEB_REPL_RENEWAL')

    if not x_replit_token or not hostname:
        print("[EMAIL] Weder ENV noch Replit Connector verfügbar")
        return None, None

    try:
        import requests
        response = requests.get(
            f'https://{hostname}/api/v2/connection?include_secrets=true&connector_names=resend',
            headers={
                'Accept': 'application/json',
                'X_REPLIT_TOKEN': x_replit_token
            },
            timeout=10)
        data = response.json()
        connection = data.get('items', [{}])[0] if data.get('items') else {}
        settings = connection.get('settings', {})

        api_key = settings.get('api_key')
        from_email = settings.get('from_email')

        if api_key:
            print(f"[EMAIL] Resend API-Key über Replit Connector gefunden")
            return api_key, from_email
        else:
            print("[EMAIL] Resend nicht konfiguriert")
            return None, None

    except Exception as e:
        print(f"[EMAIL] Fehler beim Abrufen der Resend-Credentials: {e}")
        return None, None


def send_email_resend(to_email, subject, body_html, body_text=None):
    """Sendet E-Mail über Resend API"""
    logger = logging.getLogger(__name__)

    logger.info(f"Versuche E-Mail zu senden an: {to_email}")

    try:
        api_key, from_email = get_resend_credentials()

        if not api_key:
            print(
                f"[EMAIL] WARNUNG: Resend nicht konfiguriert - E-Mail an {to_email} nicht gesendet"
            )
            return False

        resend.api_key = api_key

        from_address = "SportOase <mauro@sportoase.app>"

        params = {
            "from": from_address,
            "to": [to_email],
            "subject": subject,
            "html": body_html,
        }

        if body_text:
            params["text"] = body_text

        print(f"[EMAIL] Sende von {from_address} an {to_email}...")
        result = resend.Emails.send(params)

        print(
            f"[EMAIL] Erfolgreich gesendet an {to_email} (ID: {result.get('id', 'unknown')})"
        )
        return True

    except Exception as e:
        print(f"[EMAIL] FEHLER beim E-Mail-Versand an {to_email}: {e}")
        return False


def get_email_styles():
    """Zentrale Styles für alle E-Mails"""
    return {
        'container': 'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;',
        'header': 'background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); padding: 24px 30px; border-radius: 12px 12px 0 0;',
        'header_text': 'color: white; margin: 0; font-size: 20px; font-weight: 600;',
        'body': 'padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px;',
        'card': 'background: #f8fafc; border-radius: 10px; padding: 20px; margin: 20px 0;',
        'info_row': 'display: flex; padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #E91E63;',
        'label': 'color: #E91E63; font-weight: 600; min-width: 100px;',
        'value': 'color: #1f2937;',
        'success_box': 'background: #dcfce7; border: 1px solid #86efac; color: #166534; padding: 16px 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;',
        'warning_box': 'background: #fef3c7; border: 1px solid #fcd34d; color: #92400e; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;',
        'error_box': 'background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;',
        'footer': 'margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;',
    }


def create_booking_notification_email(data):
    """Erstellt eine formatierte E-Mail für Buchungsbenachrichtigungen (Admin)"""
    from config import PERIOD_TIMES
    
    teacher = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date_raw = data.get("date", "")
    date = format_date_german(date_raw)
    weekday_raw = data.get("weekday", "")
    weekday = get_german_weekday(weekday_raw)
    period = data.get("period", "")
    period_time = PERIOD_TIMES.get(period, "")
    offer = data.get("offer_label", "")
    offer_type = data.get("offer_type", "")

    students_json = data.get("students_json", "[]")
    students = json.loads(students_json) if isinstance(students_json, str) else students_json
    count = len(students)

    students_html = "".join([
        f'<div style="padding: 8px 12px; background: white; border-radius: 6px; margin: 6px 0;">• {s["name"]} (Klasse {s["klasse"]})</div>'
        for s in students
    ]) if students else '<div style="color: #6b7280;">Keine Schüler*innen</div>'

    subject = f"📚 Neue Buchung: {offer} am {date}"

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 20px; background: #f3f4f6;">
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); padding: 24px 30px;">
                <h2 style="color: white; margin: 0; font-size: 20px;">📚 Neue Buchung eingegangen</h2>
            </div>
            <div style="padding: 30px;">
                <div style="background: #f8fafc; border-radius: 10px; padding: 20px;">
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #3b82f6;">
                        <strong style="color: #3b82f6;">👤 Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #3b82f6;">
                        <strong style="color: #3b82f6;">📅 Datum:</strong> {weekday}, {date}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #3b82f6;">
                        <strong style="color: #3b82f6;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #3b82f6;">
                        <strong style="color: #3b82f6;">📋 Angebot:</strong> {offer} <span style="background: #3b82f6; color: white; padding: 2px 10px; border-radius: 12px; font-size: 11px; margin-left: 8px;">{offer_type.upper()}</span>
                    </div>
                    <div style="padding: 16px; background: white; border-radius: 8px; margin: 12px 0;">
                        <strong style="color: #3b82f6;">👥 Schüler*innen ({count}):</strong>
                        <div style="margin-top: 10px;">{students_html}</div>
                    </div>
                </div>
                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;">
                    Automatisch generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}<br>
                    SportOase – Ernst-Reuter-Schule Pattensen
                </div>
            </div>
        </div>
    </body></html>
    """

    text = f"""
Neue Buchung – SportOase

Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer} ({offer_type})

Schüler*innen ({count}):
{', '.join([f"{s['name']} ({s['klasse']})" for s in students])}

---
Automatisch generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}
    """

    return subject, html, text


def send_booking_notification(data):
    """Sendet Buchungsbenachrichtigung an Admin"""
    subject, html, text = create_booking_notification_email(data)
    return send_email_resend(ADMIN_EMAIL, subject, html, text)


def create_user_confirmation_email(data):
    """Erstellt eine Bestätigungs-E-Mail für den buchenden Benutzer"""
    from config import PERIOD_TIMES
    
    teacher = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date_raw = data.get("date", "")
    date = format_date_german(date_raw)
    weekday_raw = data.get("weekday", "")
    weekday = get_german_weekday(weekday_raw)
    period = data.get("period", "")
    period_time = PERIOD_TIMES.get(period, "")
    offer = data.get("offer_label", "")
    offer_type = data.get("offer_type", "")

    students_json = data.get("students_json", "[]")
    students = json.loads(students_json) if isinstance(students_json, str) else students_json
    count = len(students)

    students_html = "".join([
        f'<div style="padding: 8px 12px; background: white; border-radius: 6px; margin: 6px 0;">• {s["name"]} (Klasse {s["klasse"]})</div>'
        for s in students
    ]) if students else '<div style="color: #6b7280;">Keine Schüler*innen</div>'

    subject = f"✅ Buchung bestätigt: {offer} am {date}"

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 20px; background: #f3f4f6;">
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); padding: 24px 30px;">
                <h2 style="color: white; margin: 0; font-size: 20px;">✅ Buchung bestätigt</h2>
            </div>
            <div style="padding: 30px;">
                <div style="background: #dcfce7; border: 1px solid #86efac; color: #166534; padding: 16px 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <strong>🎉 Deine Buchung wurde erfolgreich gespeichert!</strong>
                </div>
                <div style="background: #f8fafc; border-radius: 10px; padding: 20px;">
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #E91E63;">
                        <strong style="color: #E91E63;">👤 Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #E91E63;">
                        <strong style="color: #E91E63;">📅 Datum:</strong> {weekday}, {date}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #E91E63;">
                        <strong style="color: #E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #E91E63;">
                        <strong style="color: #E91E63;">📋 Angebot:</strong> {offer} <span style="background: #E91E63; color: white; padding: 2px 10px; border-radius: 12px; font-size: 11px; margin-left: 8px;">{offer_type.upper()}</span>
                    </div>
                    <div style="padding: 16px; background: white; border-radius: 8px; margin: 12px 0;">
                        <strong style="color: #E91E63;">👥 Angemeldete Schüler*innen ({count}):</strong>
                        <div style="margin-top: 10px;">{students_html}</div>
                    </div>
                </div>
                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;">
                    Bei Fragen melde dich gerne bei Mauro.<br>
                    SportOase – Ernst-Reuter-Schule Pattensen
                </div>
            </div>
        </div>
    </body></html>
    """

    text = f"""
Buchung bestätigt – SportOase

Deine Buchung wurde erfolgreich gespeichert!

Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer} ({offer_type})

Angemeldete Schüler*innen ({count}):
{', '.join([f"{s['name']} ({s['klasse']})" for s in students])}

---
Bei Fragen melde dich gerne bei Mauro.
SportOase – Ernst-Reuter-Schule Pattensen
    """

    return subject, html, text


def send_user_booking_confirmation(email, data):
    """Sendet Buchungsbestätigung an den buchenden Benutzer"""
    subject, html, text = create_user_confirmation_email(data)
    return send_email_resend(email, subject, html, text)


def send_exclusive_pending_email(email, data):
    """Sendet E-Mail bei ausstehender Einzelbuchung (Freigabe erforderlich)"""
    from config import PERIOD_TIMES
    
    students = data.get('students', [])
    if not students:
        return False
    
    student = students[0]
    student_name = student.get('name', 'Unbekannt')
    student_class = student.get('klasse', '')
    
    teacher = data.get('teacher_name', 'Unbekannt')
    teacher_class = data.get('teacher_class', '')
    date = format_date_german(data.get('date', 'Unbekannt'))
    weekday_raw = data.get('weekday', '')
    weekday = get_german_weekday(weekday_raw)
    period = data.get('period', '?')
    period_time = PERIOD_TIMES.get(period, "")
    offer = data.get('offer_label', 'Unbekannt')
    
    subject = f"⏳ Einzelbuchung angefragt – Warte auf Freigabe"
    
    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 20px; background: #f3f4f6;">
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); padding: 24px 30px;">
                <h2 style="color: white; margin: 0; font-size: 20px;">⏳ Einzelbuchung angefragt</h2>
            </div>
            <div style="padding: 30px;">
                <div style="background: #fef3c7; border: 1px solid #fcd34d; color: #92400e; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;">
                    <strong>⚠️ Deine Buchung wartet auf Freigabe durch Mauro</strong>
                    <p style="margin: 10px 0 0 0; font-size: 14px;">Du bekommst eine E-Mail, sobald deine Anfrage bearbeitet wurde.</p>
                </div>
                <div style="background: #f8fafc; border-radius: 10px; padding: 20px;">
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #f59e0b;">
                        <strong style="color: #E91E63;">👤 Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #f59e0b;">
                        <strong style="color: #E91E63;">📅 Datum:</strong> {weekday}, {date}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #f59e0b;">
                        <strong style="color: #E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #f59e0b;">
                        <strong style="color: #E91E63;">📋 Angebot:</strong> {offer}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #f59e0b;">
                        <strong style="color: #E91E63;">👤 Schüler*in:</strong> {student_name} (Klasse {student_class})
                    </div>
                </div>
                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;">
                    Bei Fragen melde dich gerne bei Mauro.<br>
                    SportOase – Ernst-Reuter-Schule Pattensen
                </div>
            </div>
        </div>
    </body></html>
    """
    
    text = f"""
Einzelbuchung angefragt – SportOase

Deine Buchung wartet auf Freigabe durch Mauro.
Du bekommst eine E-Mail, sobald deine Anfrage bearbeitet wurde.

Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer}
Schüler*in: {student_name} (Klasse {student_class})

---
Bei Fragen melde dich gerne bei Mauro.
SportOase – Ernst-Reuter-Schule Pattensen
    """
    
    return send_email_resend(email, subject, html, text)


def send_exclusive_approved_email(teacher_email, teacher_name, student_name, date_str, period):
    """Sendet Bestätigungs-E-Mail wenn eine exklusive Buchung genehmigt wurde"""
    from config import PERIOD_TIMES

    period_time = PERIOD_TIMES.get(period, "")
    date_formatted = format_date_german(date_str)

    subject = f"✅ Einzelbuchung genehmigt – SportOase"

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 20px; background: #f3f4f6;">
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); padding: 24px 30px;">
                <h2 style="color: white; margin: 0; font-size: 20px;">🎉 Einzelbuchung genehmigt!</h2>
            </div>
            <div style="padding: 30px;">
                <div style="background: #dcfce7; border: 1px solid #86efac; color: #166534; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;">
                    <strong>Hallo {teacher_name}!</strong>
                    <p style="margin: 10px 0 0 0;">Deine exklusive Einzelbuchung wurde <strong>von Mauro genehmigt</strong>. 🎉</p>
                </div>
                <div style="background: #f8fafc; border-radius: 10px; padding: 20px;">
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #22c55e;">
                        <strong style="color: #E91E63;">📅 Datum:</strong> {date_formatted}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #22c55e;">
                        <strong style="color: #E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #22c55e;">
                        <strong style="color: #E91E63;">👤 Schüler*in:</strong> {student_name}
                    </div>
                </div>
                <div style="background: #dbeafe; border: 1px solid #93c5fd; color: #1e40af; padding: 14px 18px; border-radius: 10px; margin-top: 20px; font-size: 14px;">
                    💡 Der Slot ist jetzt vollständig für deine*n Schüler*in reserviert.
                </div>
                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;">
                    Bei Fragen melde dich gerne bei Mauro.<br>
                    SportOase – Ernst-Reuter-Schule Pattensen
                </div>
            </div>
        </div>
    </body></html>
    """

    text = f"""
Einzelbuchung genehmigt – SportOase

Hallo {teacher_name}!

Deine exklusive Einzelbuchung wurde von Mauro genehmigt.

Datum: {date_formatted}
Zeit: {period}. Stunde ({period_time} Uhr)
Schüler*in: {student_name}

Der Slot ist jetzt vollständig für deine*n Schüler*in reserviert.

---
Bei Fragen melde dich gerne bei Mauro.
SportOase – Ernst-Reuter-Schule Pattensen
    """

    return send_email_resend(teacher_email, subject, html, text)


def send_exclusive_rejected_email(teacher_email, teacher_name, student_name, date_str, period, rejection_reason=None):
    """Sendet Ablehnungs-E-Mail wenn eine exklusive Buchung abgelehnt wurde"""
    from config import PERIOD_TIMES

    period_time = PERIOD_TIMES.get(period, "")
    date_formatted = format_date_german(date_str)
    
    reason_html = ""
    reason_text = ""
    if rejection_reason:
        reason_html = f"""
            <div style="background: #fef3c7; border: 1px solid #fcd34d; color: #92400e; padding: 14px 18px; border-radius: 10px; margin: 16px 0;">
                <strong>💬 Begründung von Mauro:</strong><br>
                <span style="display: block; margin-top: 8px;">{rejection_reason}</span>
            </div>
        """
        reason_text = f"\nBegründung von Mauro:\n{rejection_reason}\n"

    subject = f"❌ Einzelbuchung abgelehnt – SportOase"

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 20px; background: #f3f4f6;">
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); padding: 24px 30px;">
                <h2 style="color: white; margin: 0; font-size: 20px;">Einzelbuchung abgelehnt</h2>
            </div>
            <div style="padding: 30px;">
                <div style="background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;">
                    <strong>Hallo {teacher_name},</strong>
                    <p style="margin: 10px 0 0 0;">Leider wurde deine exklusive Einzelbuchung <strong>von Mauro abgelehnt</strong>.</p>
                </div>
                <div style="background: #f8fafc; border-radius: 10px; padding: 20px;">
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">📅 Datum:</strong> {date_formatted}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">👤 Schüler*in:</strong> {student_name}
                    </div>
                </div>
                {reason_html}
                <div style="background: #f0f9ff; border: 1px solid #bae6fd; color: #0369a1; padding: 14px 18px; border-radius: 10px; margin-top: 16px; font-size: 14px;">
                    💡 Du kannst deine*n Schüler*in gerne regulär (ohne exklusive Reservierung) anmelden, falls Plätze verfügbar sind.
                </div>
                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;">
                    Bei Fragen melde dich gerne bei Mauro.<br>
                    SportOase – Ernst-Reuter-Schule Pattensen
                </div>
            </div>
        </div>
    </body></html>
    """

    text = f"""
Einzelbuchung abgelehnt – SportOase

Hallo {teacher_name},

Leider wurde deine exklusive Einzelbuchung von Mauro abgelehnt.

Datum: {date_formatted}
Zeit: {period}. Stunde ({period_time} Uhr)
Schüler*in: {student_name}
{reason_text}
Du kannst deine*n Schüler*in gerne regulär (ohne exklusive Reservierung) anmelden, falls Plätze verfügbar sind.

---
Bei Fragen melde dich gerne bei Mauro.
SportOase – Ernst-Reuter-Schule Pattensen
    """

    return send_email_resend(teacher_email, subject, html, text)


def send_booking_removed_due_to_exclusive(teacher_email, teacher_name, booking_info, exclusive_info):
    """Sendet E-Mail wenn eine Buchung wegen genehmigter Exklusivbuchung entfernt wurde"""
    from config import PERIOD_TIMES
    
    date_formatted = format_date_german(booking_info.get('date', 'Unbekannt'))
    period = booking_info.get('period', '?')
    period_time = PERIOD_TIMES.get(period, "")
    students = booking_info.get('students', [])
    offer = booking_info.get('offer_label', 'Unbekannt')
    
    students_html = "".join([
        f'<div style="padding: 6px 10px; background: white; border-radius: 4px; margin: 4px 0;">• {s.get("name", "?")} (Klasse {s.get("klasse", "?")})</div>'
        for s in students
    ]) if students else '<div>Keine Schüler*innen</div>'
    
    students_list = ", ".join([f"{s.get('name', '?')} ({s.get('klasse', '?')})" for s in students])
    
    subject = f"⚠️ Buchung storniert – SportOase"
    
    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 20px; background: #f3f4f6;">
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); padding: 24px 30px;">
                <h2 style="color: white; margin: 0; font-size: 20px;">⚠️ Buchung storniert</h2>
            </div>
            <div style="padding: 30px;">
                <div style="background: #fef3c7; border: 1px solid #fcd34d; color: #92400e; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;">
                    <strong>Hallo {teacher_name},</strong>
                    <p style="margin: 10px 0 0 0;">Leider wurde deine Buchung automatisch storniert, da eine <strong>exklusive Einzelbuchung</strong> für denselben Slot von Mauro genehmigt wurde.</p>
                </div>
                <div style="background: #f8fafc; border-radius: 10px; padding: 20px;">
                    <h4 style="margin: 0 0 15px 0; color: #E91E63; font-size: 14px;">📋 Deine stornierte Buchung:</h4>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">📅 Datum:</strong> {date_formatted}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">📚 Angebot:</strong> {offer}
                    </div>
                    <div style="padding: 12px 16px; background: white; border-radius: 8px; margin: 8px 0; border-left: 4px solid #ef4444;">
                        <strong style="color: #E91E63;">👥 Schüler*innen:</strong>
                        <div style="margin-top: 8px;">{students_html}</div>
                    </div>
                </div>
                <div style="background: #f0f9ff; border: 1px solid #bae6fd; color: #0369a1; padding: 14px 18px; border-radius: 10px; margin-top: 16px; font-size: 14px;">
                    💡 Bitte buche deine Schüler*innen für einen anderen Slot neu ein.
                </div>
                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px;">
                    Bei Fragen melde dich gerne bei Mauro.<br>
                    SportOase – Ernst-Reuter-Schule Pattensen
                </div>
            </div>
        </div>
    </body></html>
    """
    
    text = f"""
Buchung storniert – SportOase

Hallo {teacher_name},

Leider wurde deine Buchung automatisch storniert, da eine exklusive Einzelbuchung für denselben Slot von Mauro genehmigt wurde.

Deine stornierte Buchung:
- Datum: {date_formatted}
- Zeit: {period}. Stunde ({period_time} Uhr)
- Angebot: {offer}
- Schüler*innen: {students_list}

Bitte buche deine Schüler*innen für einen anderen Slot neu ein.

---
Bei Fragen melde dich gerne bei Mauro.
SportOase – Ernst-Reuter-Schule Pattensen
    """
    
    return send_email_resend(teacher_email, subject, html, text)
