"""
dynamic_config.py – DB-backed Ersatz für hardcoded config.py Werte
Stunden, Kurse (fest/frei) und Schulklassen werden aus der Datenbank geladen.
Beim ersten Start werden die Standardwerte aus config.py automatisch eingesät.
"""

from database import db


# ─── Fallback-Defaults aus config.py ────────────────────────────────────────

_DEFAULT_PERIOD_TIMES = {
    1: {"start": "07:50", "end": "08:35", "name": "1. Stunde"},
    2: {"start": "08:35", "end": "09:20", "name": "2. Stunde"},
    3: {"start": "09:40", "end": "10:25", "name": "3. Stunde"},
    4: {"start": "10:25", "end": "11:20", "name": "4. Stunde"},
    5: {"start": "11:40", "end": "12:25", "name": "5. Stunde"},
    6: {"start": "12:25", "end": "13:10", "name": "6. Stunde"},
}

_DEFAULT_FIXED_OFFERS = {
    "Mon": {1: "Wochenstart-Aktivierung", 3: "Konflikt-Reset & Deeskalation", 5: "Koordinationszirkel"},
    "Tue": {},
    "Wed": {1: "Sozialtraining / Gruppenreset", 3: "Aktivierung Mini-Fitness", 5: "Motorik-Parcours"},
    "Thu": {2: "Konflikt-Reset", 5: "Turnen + Balance"},
    "Fri": {2: "Atem & Reflexion", 4: "Bodyscan Light", 5: "Ruhezone / Entspannung"},
}

_DEFAULT_FREE_MODULES = [
    "Aktivierung",
    "Regulation / Entspannung",
    "Konflikt-Reset",
    "Egal / flexibel",
]

_DEFAULT_SCHOOL_CLASSES = [
    "5a", "5b", "5c",
    "6a", "6b", "6c",
    "7a", "7b", "7c",
    "8a", "8b", "8c",
    "9a", "9b", "9c",
    "10a", "10b", "10c",
]

_DEFAULT_MAX_STUDENTS = 5
_DEFAULT_ADVANCE_MINUTES = 60


# ─── Seeding ─────────────────────────────────────────────────────────────────

def seed_initial_data():
    """
    Befüllt die Tabellen periods, courses und school_classes mit den Standardwerten
    aus config.py, falls die Tabellen noch leer sind.
    Wird beim App-Start aufgerufen.
    """
    from models import Period, Course, SchoolClass
    from system_config import get_config, set_config

    try:
        # Stunden
        if Period.query.count() == 0:
            for num, data in _DEFAULT_PERIOD_TIMES.items():
                p = Period(
                    number=num,
                    name=data['name'],
                    start_time=data['start'],
                    end_time=data['end'],
                    sort_order=num,
                    is_active=True,
                )
                db.session.add(p)
            print("[DynConfig] Stunden aus Defaults eingesät.")

        # Kurse
        if Course.query.count() == 0:
            order = 0
            # Feste Angebote
            for weekday, periods in _DEFAULT_FIXED_OFFERS.items():
                for period_num, name in periods.items():
                    c = Course(
                        name=name,
                        course_type='fixed',
                        weekday=weekday,
                        period_number=period_num,
                        is_active=True,
                        sort_order=order,
                    )
                    db.session.add(c)
                    order += 1
            # Freie Module
            for name in _DEFAULT_FREE_MODULES:
                c = Course(
                    name=name,
                    course_type='free',
                    weekday=None,
                    period_number=None,
                    is_active=True,
                    sort_order=order,
                )
                db.session.add(c)
                order += 1
            print("[DynConfig] Kurse aus Defaults eingesät.")

        # Schulklassen
        if SchoolClass.query.count() == 0:
            for i, name in enumerate(_DEFAULT_SCHOOL_CLASSES):
                sc = SchoolClass(name=name, sort_order=i, is_active=True)
                db.session.add(sc)
            print("[DynConfig] Schulklassen aus Defaults eingesät.")

        # SystemConfig-Defaults für max_students und advance_minutes
        if get_config('max_students_per_period') is None:
            set_config('max_students_per_period', str(_DEFAULT_MAX_STUDENTS), category='booking')
        if get_config('booking_advance_minutes') is None:
            set_config('booking_advance_minutes', str(_DEFAULT_ADVANCE_MINUTES), category='booking')

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[DynConfig] Seeding fehlgeschlagen: {e}")


# ─── Öffentliche Lese-Funktionen ──────────────────────────────────────────────

def get_period_times():
    """Gibt alle Stunden als Dict zurück: {number: {'start': '...', 'end': '...', 'name': '...'}}"""
    from models import Period
    try:
        periods = Period.query.filter_by(is_active=True).order_by(Period.sort_order).all()
        if not periods:
            return _DEFAULT_PERIOD_TIMES
        return {p.number: {'start': p.start_time, 'end': p.end_time, 'name': p.name} for p in periods}
    except Exception:
        return _DEFAULT_PERIOD_TIMES


def get_period(number):
    """Gibt eine einzelne Stunde zurück: {'start': '...', 'end': '...', 'name': '...'}"""
    from models import Period
    try:
        p = Period.query.filter_by(number=number, is_active=True).first()
        if p:
            return {'start': p.start_time, 'end': p.end_time, 'name': p.name}
    except Exception:
        pass
    return _DEFAULT_PERIOD_TIMES.get(number, {'start': '?', 'end': '?', 'name': f'{number}. Stunde'})


def get_fixed_offers():
    """Gibt feste Angebote als Dict zurück: {'Mon': {1: 'Name', ...}, ...}"""
    from models import Course
    try:
        courses = Course.query.filter_by(course_type='fixed', is_active=True).all()
        if not courses:
            return _DEFAULT_FIXED_OFFERS
        result = {wd: {} for wd in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri')}
        for c in courses:
            if c.weekday and c.period_number is not None:
                result.setdefault(c.weekday, {})[c.period_number] = c.name
        return result
    except Exception:
        return _DEFAULT_FIXED_OFFERS


def get_free_courses():
    """Gibt freie Module als Liste zurück."""
    from models import Course
    try:
        courses = Course.query.filter_by(course_type='free', is_active=True).order_by(Course.sort_order).all()
        if not courses:
            return _DEFAULT_FREE_MODULES
        return [c.name for c in courses]
    except Exception:
        return _DEFAULT_FREE_MODULES


def get_school_classes_list():
    """Gibt Schulklassen als sortierte Liste zurück."""
    from models import SchoolClass
    try:
        classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.sort_order, SchoolClass.name).all()
        if not classes:
            return _DEFAULT_SCHOOL_CLASSES
        return [sc.name for sc in classes]
    except Exception:
        return _DEFAULT_SCHOOL_CLASSES


def get_max_students():
    """Gibt die maximale Schüleranzahl pro Stunde zurück."""
    from system_config import get_config
    try:
        val = get_config('max_students_per_period')
        if val is not None:
            return int(val)
    except Exception:
        pass
    return _DEFAULT_MAX_STUDENTS


def get_booking_advance_minutes():
    """Gibt die Minuten zurück, die eine Buchung im Voraus erfolgen muss."""
    from system_config import get_config
    try:
        val = get_config('booking_advance_minutes')
        if val is not None:
            return int(val)
    except Exception:
        pass
    return _DEFAULT_ADVANCE_MINUTES
