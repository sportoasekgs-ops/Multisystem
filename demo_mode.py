"""
Demo-Modus für SportOase.
Wenn aktiv: Fake-Buchungen werden angezeigt, kein echter E-Mail-Versand,
Demo-Badge erscheint in der Navbar.
"""

from system_config import get_config, set_config


def is_demo_mode() -> bool:
    """Gibt True zurück, wenn der Demo-Modus aktiv ist."""
    return get_config('demo_mode', 'false') == 'true'


def enable_demo_mode():
    set_config('demo_mode', 'true', category='system')


def disable_demo_mode():
    set_config('demo_mode', 'false', category='system')


# ── Fake-Buchungen für den Demo-Modus ────────────────────────────────────────

import json
from datetime import date, timedelta

def _next_weekday(weekday_num: int) -> str:
    """Gibt das Datum des nächsten Wochentags zurück (0=Mo … 4=Fr)."""
    today = date.today()
    days_ahead = weekday_num - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

WEEKDAY_ABBRS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

DEMO_BOOKINGS = [
    {
        'id': -1,
        'date': _next_weekday(0),
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
        'date': _next_weekday(1),
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
        'date': _next_weekday(3),
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
    return [b for b in DEMO_BOOKINGS if start_date <= b['date'] <= end_date]


def get_demo_bookings_for_date(date_str: str) -> list:
    return [b for b in DEMO_BOOKINGS if b['date'] == date_str]


def send_demo_email_log(to_email: str, subject: str) -> bool:
    """Simuliert E-Mail-Versand im Demo-Modus (nur Logging, kein echter Versand)."""
    print(f"[DEMO-MODUS] E-Mail NICHT gesendet (Demo-Modus aktiv)")
    print(f"[DEMO-MODUS]   An: {to_email}")
    print(f"[DEMO-MODUS]   Betreff: {subject}")
    return True
