"""
Demo-Modus für das Buchungssystem.
Wenn aktiv: Fake-Buchungen werden angezeigt, kein echter E-Mail-Versand,
Demo-Badge erscheint in der Navbar.
"""

import json
from datetime import date, datetime, timedelta

from system_config import get_config, set_config


def is_demo_mode() -> bool:
    """Gibt True zurück, wenn der Demo-Modus aktiv ist."""
    return get_config('demo_mode', 'false') == 'true'


def enable_demo_mode():
    set_config('demo_mode', 'true', category='system')


def disable_demo_mode():
    set_config('demo_mode', 'false', category='system')


# ── Fake-Buchungen für den Demo-Modus ────────────────────────────────────────

def _build_demo_bookings(monday_date):
    """Generiert Demo-Buchungen für die Woche ab monday_date."""
    mo = monday_date
    tu = mo + timedelta(days=1)
    th = mo + timedelta(days=3)

    return [
        {
            'id': -1,
            'date': mo.strftime('%Y-%m-%d'),
            'weekday': 'Mon',
            'period': 2,
            'teacher_id': -1,
            'teacher_name': 'M. Mustermann',
            'teacher_class': '7a',
            'students_json': json.dumps([
                {'name': 'Lena S.', 'klasse': '7a'},
                {'name': 'Tim K.', 'klasse': '7a'},
            ]),
            'offer_type': 'fest',
            'offer_label': 'Koordinationszirkel',
            'notes': '',
            'is_exclusive': False,
            'is_approved': True,
            'created_at': None,
            'teacher_email': None,
            'calendar_event_id': None,
        },
        {
            'id': -2,
            'date': tu.strftime('%Y-%m-%d'),
            'weekday': 'Tue',
            'period': 3,
            'teacher_id': -1,
            'teacher_name': 'A. Beispiel',
            'teacher_class': '9b',
            'students_json': json.dumps([
                {'name': 'Max M.', 'klasse': '9b'},
                {'name': 'Sophie R.', 'klasse': '9b'},
                {'name': 'Jonas W.', 'klasse': '9b'},
            ]),
            'offer_type': 'frei',
            'offer_label': 'Freie Wahl',
            'notes': 'Demo-Buchung',
            'is_exclusive': False,
            'is_approved': True,
            'created_at': None,
            'teacher_email': None,
            'calendar_event_id': None,
        },
        {
            'id': -3,
            'date': th.strftime('%Y-%m-%d'),
            'weekday': 'Thu',
            'period': 1,
            'teacher_id': -1,
            'teacher_name': 'K. Lehmann',
            'teacher_class': '5c',
            'students_json': json.dumps([
                {'name': 'Mia F.', 'klasse': '5c'},
            ]),
            'offer_type': 'fest',
            'offer_label': 'Sozialtraining',
            'notes': '',
            'is_exclusive': True,
            'is_approved': True,
            'created_at': None,
            'teacher_email': None,
            'calendar_event_id': None,
        },
    ]


def get_demo_bookings_for_week(start_date: str, end_date: str) -> list:
    """Gibt Demo-Buchungen zurück, die in den angegebenen Zeitraum fallen."""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return []
    # Montag der angefragten Woche ermitteln
    monday = start - timedelta(days=start.weekday())
    bookings = _build_demo_bookings(monday)
    return [b for b in bookings if start_date <= b['date'] <= end_date]


def get_demo_bookings_for_date(date_str: str) -> list:
    """Gibt Demo-Buchungen für ein bestimmtes Datum zurück."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return []
    monday = d - timedelta(days=d.weekday())
    bookings = _build_demo_bookings(monday)
    return [b for b in bookings if b['date'] == date_str]


def send_demo_email_log(to_email: str, subject: str) -> bool:
    """Simuliert E-Mail-Versand im Demo-Modus (nur Logging, kein echter Versand)."""
    print(f"[DEMO-MODUS] E-Mail NICHT gesendet (Demo-Modus aktiv)")
    print(f"[DEMO-MODUS]   An: {to_email}")
    print(f"[DEMO-MODUS]   Betreff: {subject}")
    return True
