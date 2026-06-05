"""
dynamic_config.py – DB-backed Ersatz für hardcoded config.py Werte
Stunden, Kurse (fest/frei) und Schulklassen werden aus der Datenbank geladen.
Nach Factory Reset wird NICHTS automatisch eingesät – Setup-Wizard ist zuständig.
"""

from database import db


_DEFAULT_PERIOD_TIMES = {
    1: {"start": "07:50", "end": "08:35", "name": "1. Stunde", "kind": "lesson"},
    2: {"start": "08:35", "end": "09:20", "name": "2. Stunde", "kind": "lesson"},
    3: {"start": "09:20", "end": "09:40", "name": "Große Pause", "kind": "break"},
    4: {"start": "09:40", "end": "10:25", "name": "3. Stunde", "kind": "lesson"},
    5: {"start": "10:25", "end": "11:10", "name": "4. Stunde", "kind": "lesson"},
    6: {"start": "11:10", "end": "11:30", "name": "Große Pause", "kind": "break"},
    7: {"start": "11:30", "end": "12:15", "name": "5. Stunde", "kind": "lesson"},
    8: {"start": "12:15", "end": "13:00", "name": "6. Stunde", "kind": "lesson"},
}

_DEFAULT_MAX_STUDENTS = 5
_DEFAULT_ADVANCE_MINUTES = 60


def invalidate_periods_cache():
    """Request-Cache für Stunden/Kurse nach Admin-Änderungen leeren."""
    try:
        from flask import g, has_request_context

        if has_request_context():
            for attr in list(vars(g)):
                if attr.startswith("_periods_cache") or attr.startswith("_fixed_offers_cache") or attr.startswith("_room_periods_"):
                    delattr(g, attr)
    except Exception:
        pass


def _period_entry(p):
    kind = getattr(p, "period_kind", None) or "lesson"
    after_lesson = getattr(p, "after_lesson", None)
    name = p.name
    if kind == "break" and after_lesson:
        name = f"{p.name} (nach {after_lesson}. Stunde)"
    return {
        "start": p.start_time,
        "end": p.end_time,
        "name": name,
        "kind": kind,
        "is_break": kind == "break",
        "after_lesson": after_lesson,
    }


def _room_period_entry(rp):
    """RoomPeriod → dict (gleiche Struktur wie _period_entry)."""
    kind = rp.period_kind or "lesson"
    name = rp.name
    if kind == "break" and rp.after_lesson:
        name = f"{rp.name} (nach {rp.after_lesson}. Stunde)"
    return {
        "start": rp.start_time,
        "end": rp.end_time,
        "name": name,
        "kind": kind,
        "is_break": kind == "break",
        "after_lesson": rp.after_lesson,
    }


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
        if get_config("max_students_per_period") is None:
            set_config(
                "max_students_per_period",
                str(_DEFAULT_MAX_STUDENTS),
                category="booking",
            )
        if get_config("booking_advance_minutes") is None:
            set_config(
                "booking_advance_minutes",
                str(_DEFAULT_ADVANCE_MINUTES),
                category="booking",
            )

        if is_setup_complete() and Period.query.count() == 0:
            for num, data in _DEFAULT_PERIOD_TIMES.items():
                p = Period(
                    number=num,
                    name=data["name"],
                    start_time=data["start"],
                    end_time=data["end"],
                    sort_order=num,
                    is_active=True,
                    period_kind=data.get("kind", "lesson"),
                )
                db.session.add(p)
            print("[DynConfig] Stunden aus Defaults eingesät (Upgrade alter Installation).")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[DynConfig] Seeding fehlgeschlagen: {e}")


def _query_active_periods_cached():
    """Aktive Zeitfenster einmal pro Request laden."""
    try:
        from flask import g, has_request_context

        if has_request_context():
            if hasattr(g, "_periods_cache"):
                return g._periods_cache
            from models import Period

            result = (
                Period.query.filter_by(is_active=True)
                .order_by(Period.sort_order, Period.number)
                .all()
            )
            g._periods_cache = result
            return result
    except Exception:
        pass
    from models import Period

    return (
        Period.query.filter_by(is_active=True)
        .order_by(Period.sort_order, Period.number)
        .all()
    )


def _get_room_periods_cached(room_id):
    """Raumspezifische Stunden laden (mit Request-Cache)."""
    try:
        from flask import g, has_request_context
        if has_request_context():
            cache_key = f"_room_periods_{room_id}"
            if hasattr(g, cache_key):
                return getattr(g, cache_key)
            from models import Room, RoomPeriod
            room = Room.query.get(room_id)
            if room and room.use_custom_schedule:
                result = (
                    RoomPeriod.query.filter_by(room_id=room_id, is_active=True)
                    .order_by(RoomPeriod.sort_order, RoomPeriod.period_number)
                    .all()
                )
                if result:
                    setattr(g, cache_key, result)
                    return result
            return None  # None = use global fallback
    except Exception:
        pass
    # Outside request context: query directly
    from models import Room, RoomPeriod
    try:
        room = Room.query.get(room_id)
        if room and room.use_custom_schedule:
            result = (
                RoomPeriod.query.filter_by(room_id=room_id, is_active=True)
                .order_by(RoomPeriod.sort_order, RoomPeriod.period_number)
                .all()
            )
            return result if result else None
    except Exception:
        pass
    return None


def get_period_times(room_id=None):
    """Alle aktiven Zeitfenster (Unterricht + große Pausen), sortiert.
    Bei room_id: raumspezifisch, falls Custom-Schedule aktiv."""
    if room_id:
        room_periods = _get_room_periods_cached(room_id)
        if room_periods is not None:
            return {rp.period_number: _room_period_entry(rp) for rp in room_periods}
    # Global fallback
    from system_config import is_setup_complete

    try:
        periods = _query_active_periods_cached()
        if not periods:
            if is_setup_complete():
                return _DEFAULT_PERIOD_TIMES
            return {}
        return {p.number: _period_entry(p) for p in periods}
    except Exception:
        return _DEFAULT_PERIOD_TIMES


def get_ordered_period_numbers(room_id=None):
    """Interne Perioden-Nummern in Anzeigereihenfolge (sort_order), nicht nach Nummer."""
    if room_id:
        room_periods = _get_room_periods_cached(room_id)
        if room_periods is not None:
            return [rp.period_number for rp in room_periods]
    # Global fallback
    from system_config import is_setup_complete

    try:
        periods = _query_active_periods_cached()
        if periods:
            return [p.number for p in periods]
        if is_setup_complete():
            return list(_DEFAULT_PERIOD_TIMES.keys())
        return []
    except Exception:
        return list(_DEFAULT_PERIOD_TIMES.keys())


def is_break_period(number, room_id=None):
    data = get_period_times(room_id=room_id).get(number, {})
    return data.get("is_break", False)


def get_period(number, room_id=None):
    if room_id:
        room_data = get_period_times(room_id=room_id).get(number)
        if room_data:
            return room_data
    from models import Period

    try:
        p = Period.query.filter_by(number=number, is_active=True).first()
        if p:
            return _period_entry(p)
    except Exception:
        pass
    fallback = _DEFAULT_PERIOD_TIMES.get(number)
    if fallback:
        return dict(fallback)
    return {
        "start": "?",
        "end": "?",
        "name": f"{number}. Stunde",
        "kind": "lesson",
        "is_break": False,
    }


def format_period_label(number, include_time=False, room_id=None):
    """Kurzes Anzeige-Label (Name der Stunde/Pause, optional mit Uhrzeit)."""
    p = get_period(number, room_id=room_id)
    name = p.get("name") or f"{number}. Stunde"
    if include_time and p.get("start") and p.get("end"):
        return f"{name} ({p['start']}–{p['end']})"
    return name


def get_fixed_offers(room_id=None):
    """Feste Angebote aus DB. Bei room_id: raumspezifisch."""
    if room_id:
        from models import Room, RoomCourse
        try:
            room = Room.query.get(room_id)
            if room and room.use_custom_schedule:
                result = {wd: {} for wd in ("Mon", "Tue", "Wed", "Thu", "Fri")}
                for rc in RoomCourse.query.filter_by(room_id=room_id).join(RoomCourse.course).all():
                    if rc.course and rc.weekday and rc.course.is_active:
                        result.setdefault(rc.weekday, {})[rc.period_number] = rc.course.name
                return result
        except Exception:
            pass

    # Global fallback (original code)
    try:
        from flask import g, has_request_context

        if has_request_context():
            if hasattr(g, "_fixed_offers_cache"):
                return g._fixed_offers_cache
    except Exception:
        pass

    from models import Course

    try:
        courses = Course.query.filter_by(course_type="fixed", is_active=True, room_id=None).all()
        result = {wd: {} for wd in ("Mon", "Tue", "Wed", "Thu", "Fri")}
        for c in courses:
            if c.weekday and c.period_number is not None:
                result.setdefault(c.weekday, {})[c.period_number] = c.name
    except Exception:
        result = {wd: {} for wd in ("Mon", "Tue", "Wed", "Thu", "Fri")}

    try:
        from flask import g, has_request_context

        if has_request_context():
            g._fixed_offers_cache = result
    except Exception:
        pass
    return result


def get_free_courses(room_id=None):
    """Freie Module aus DB. Leere Liste wenn keine. Bei room_id: raumspezifisch."""
    from models import Course, Room

    try:
        if room_id:
            room = Room.query.get(room_id)
            if room and room.use_custom_schedule:
                courses = (
                    Course.query.filter_by(course_type="free", is_active=True, room_id=room_id)
                    .order_by(Course.sort_order)
                    .all()
                )
                return [c.name for c in courses]
        
        courses = (
            Course.query.filter_by(course_type="free", is_active=True, room_id=None)
            .order_by(Course.sort_order)
            .all()
        )
        return [c.name for c in courses]
    except Exception:
        return []


def get_school_classes_list():
    """Schulklassen aus DB. Leere Liste wenn keine – KEIN Fallback auf Defaults."""
    from models import SchoolClass

    try:
        classes = (
            SchoolClass.query.filter_by(is_active=True)
            .order_by(SchoolClass.sort_order, SchoolClass.name)
            .all()
        )
        return [sc.name for sc in classes]
    except Exception:
        return []


def get_max_students():
    from system_config import get_config

    try:
        val = get_config("max_students_per_period")
        if val is not None:
            return int(val)
    except Exception:
        pass
    return _DEFAULT_MAX_STUDENTS


def get_booking_advance_minutes():
    from system_config import get_config

    try:
        val = get_config("booking_advance_minutes")
        if val is not None:
            return int(val)
    except Exception:
        pass
    return _DEFAULT_ADVANCE_MINUTES
