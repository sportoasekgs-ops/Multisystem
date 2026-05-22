"""
dynamic_config.py – DB-backed Ersatz für hardcoded config.py Werte
Stunden, Kurse (fest/frei) und Schulklassen werden aus der Datenbank geladen.
Nach Factory Reset wird NICHTS automatisch eingesät – Setup-Wizard ist zuständig.
"""

from database import db


_DEFAULT_PERIOD_TIMES = {
    1: {"start": "07:50", "end": "08:35", "name": "1. Stunde"},
    2: {"start": "08:35", "end": "09:20", "name": "2. Stunde"},
    3: {"start": "09:40", "end": "10:25", "name": "3. Stunde"},
    4: {"start": "10:25", "end": "11:20", "name": "4. Stunde"},
    5: {"start": "11:40", "end": "12:25", "name": "5. Stunde"},
    6: {"start": "12:25", "end": "13:10", "name": "6. Stunde"},
}

_DEFAULT_MAX_STUDENTS = 5
_DEFAULT_ADVANCE_MINUTES = 60


def seed_initial_data():
    """
    Sät nur SystemConfig-Defaults (max_students, advance_minutes).
    Kurse/Stunden/Klassen werden NICHT mehr automatisch eingesät –
    das ist Aufgabe des Setup-Wizards.
    Stunden werden als Fallback eingesät NUR wenn Setup abgeschlossen
    ist und die Tabelle leer ist (Upgrade aus alter Version ohne Wizard).
    """
    from models import Period
    from system_config import get_config, set_config, is_setup_complete

    try:
        if get_config('max_students_per_period') is None:
            set_config('max_students_per_period', str(_DEFAULT_MAX_STUDENTS), category='booking')
        if get_config('booking_advance_minutes') is None:
            set_config('booking_advance_minutes', str(_DEFAULT_ADVANCE_MINUTES), category='booking')

        # Stunden nur bei Upgrades (Setup abgeschlossen, aber Tabelle leer)
        if is_setup_complete() and Period.query.count() == 0:
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
            print("[DynConfig] Stunden aus Defaults eingesät (Upgrade alter Installation).")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[DynConfig] Seeding fehlgeschlagen: {e}")


def get_period_times():
    """Gibt alle Stunden als Dict zurück: {number: {'start': '...', 'end': '...', 'name': '...'}}"""
    from models import Period
    from system_config import is_setup_complete
    try:
        periods = Period.query.filter_by(is_active=True).order_by(Period.sort_order).all()
        if not periods:
            # Fallback nur wenn Setup abgeschlossen (Upgrade alter Installation)
            if is_setup_complete():
                return _DEFAULT_PERIOD_TIMES
            # Nach Ersteinrichtung: keine Stunden → leeres Dict → Dashboard zeigt nichts
            return {}
        return {p.number: {'start': p.start_time, 'end': p.end_time, 'name': p.name} for p in periods}
    except Exception:
        return _DEFAULT_PERIOD_TIMES


def get_period(number):
    from models import Period
    try:
        p = Period.query.filter_by(number=number, is_active=True).first()
        if p:
            return {'start': p.start_time, 'end': p.end_time, 'name': p.name}
    except Exception:
        pass
    return _DEFAULT_PERIOD_TIMES.get(number, {'start': '?', 'end': '?', 'name': f'{number}. Stunde'})


def get_fixed_offers():
    """Feste Angebote aus DB. Leeres Dict wenn keine Kurse – KEIN Fallback auf Defaults."""
    from models import Course
    try:
        courses = Course.query.filter_by(course_type='fixed', is_active=True).all()
        result = {wd: {} for wd in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri')}
        for c in courses:
            if c.weekday and c.period_number is not None:
                result.setdefault(c.weekday, {})[c.period_number] = c.name
        return result
    except Exception:
        return {wd: {} for wd in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri')}


def get_free_courses():
    """Freie Module aus DB. Leere Liste wenn keine – KEIN Fallback auf Defaults."""
    from models import Course
    try:
        courses = Course.query.filter_by(course_type='free', is_active=True).order_by(Course.sort_order).all()
        return [c.name for c in courses]
    except Exception:
        return []


def get_school_classes_list():
    """Schulklassen aus DB. Leere Liste wenn keine – KEIN Fallback auf Defaults."""
    from models import SchoolClass
    try:
        classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.sort_order, SchoolClass.name).all()
        return [sc.name for sc in classes]
    except Exception:
        return []


def get_max_students():
    from system_config import get_config
    try:
        val = get_config('max_students_per_period')
        if val is not None:
            return int(val)
    except Exception:
        pass
    return _DEFAULT_MAX_STUDENTS


def get_booking_advance_minutes():
    from system_config import get_config
    try:
        val = get_config('booking_advance_minutes')
        if val is not None:
            return int(val)
    except Exception:
        pass
    return _DEFAULT_ADVANCE_MINUTES
