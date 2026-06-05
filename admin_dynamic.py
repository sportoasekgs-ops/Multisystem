"""
admin_dynamic.py – Admin-Blueprint für dynamische Stunden, Kurse & Klassen
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import db
import json as _json

# Eingebaute Vorlagen (werden nicht in der DB gespeichert)
_BUILTIN_TEMPLATES = [
    {
        'id': 'builtin_6',
        'name': 'Standard Halbtagsschule (6 Stunden)',
        'description': 'Klassischer Schulvormittag von 7:50–13:10 Uhr',
        'periods': [
            {'number': 1, 'name': '1. Stunde', 'start': '07:50', 'end': '08:35', 'kind': 'lesson'},
            {'number': 2, 'name': '2. Stunde', 'start': '08:35', 'end': '09:20', 'kind': 'lesson'},
            {'number': 3, 'name': 'Große Pause', 'start': '09:20', 'end': '09:40', 'kind': 'break', 'after_lesson': 2},
            {'number': 4, 'name': '3. Stunde', 'start': '09:40', 'end': '10:25', 'kind': 'lesson'},
            {'number': 5, 'name': '4. Stunde', 'start': '10:25', 'end': '11:10', 'kind': 'lesson'},
            {'number': 6, 'name': 'Große Pause', 'start': '11:10', 'end': '11:30', 'kind': 'break', 'after_lesson': 4},
            {'number': 7, 'name': '5. Stunde', 'start': '11:30', 'end': '12:15', 'kind': 'lesson'},
            {'number': 8, 'name': '6. Stunde', 'start': '12:15', 'end': '13:00', 'kind': 'lesson'},
        ],
    },
    {
        'id': 'builtin_8',
        'name': 'Ganztagsschule (8 Stunden)',
        'description': 'Ganztag von 7:50–15:10 Uhr mit großen Pausen',
        'periods': [
            {'number': 1, 'name': '1. Stunde', 'start': '07:50', 'end': '08:35', 'kind': 'lesson'},
            {'number': 2, 'name': '2. Stunde', 'start': '08:35', 'end': '09:20', 'kind': 'lesson'},
            {'number': 3, 'name': 'Große Pause', 'start': '09:20', 'end': '09:40', 'kind': 'break', 'after_lesson': 2},
            {'number': 4, 'name': '3. Stunde', 'start': '09:40', 'end': '10:25', 'kind': 'lesson'},
            {'number': 5, 'name': '4. Stunde', 'start': '10:25', 'end': '11:10', 'kind': 'lesson'},
            {'number': 6, 'name': 'Große Pause', 'start': '11:10', 'end': '11:30', 'kind': 'break', 'after_lesson': 4},
            {'number': 7, 'name': '5. Stunde', 'start': '11:30', 'end': '12:15', 'kind': 'lesson'},
            {'number': 8, 'name': '6. Stunde', 'start': '12:15', 'end': '13:00', 'kind': 'lesson'},
            {'number': 9, 'name': 'Mittagspause', 'start': '13:00', 'end': '14:00', 'kind': 'break', 'after_lesson': 6},
            {'number': 10, 'name': '7. Stunde', 'start': '14:00', 'end': '14:45', 'kind': 'lesson'},
            {'number': 11, 'name': '8. Stunde', 'start': '14:45', 'end': '15:30', 'kind': 'lesson'},
        ],
    },
    {
        'id': 'builtin_4',
        'name': 'Kurzer Schultag (4 Stunden)',
        'description': 'Kompakter Vormittag von 8:00–11:35 Uhr',
        'periods': [
            {'number': 1, 'name': '1. Stunde', 'start': '08:00', 'end': '08:45'},
            {'number': 2, 'name': '2. Stunde', 'start': '08:45', 'end': '09:30'},
            {'number': 3, 'name': '3. Stunde', 'start': '09:50', 'end': '10:35'},
            {'number': 4, 'name': '4. Stunde', 'start': '10:35', 'end': '11:20'},
        ],
    },
]

admin_dyn_bp = Blueprint('admin_dyn', __name__, url_prefix='/admin')


def _admin_required():
    from models import get_user_by_id
    if 'user_id' not in session:
        return False
    user = get_user_by_id(session['user_id'])
    return user and user['role'] == 'admin'


def _validate_csrf(token):
    return token == session.get('csrf_token')


def _after_periods_changed():
    from dynamic_config import invalidate_periods_cache

    invalidate_periods_cache()


def _parse_hm(time_str):
    parts = (time_str or '00:00').strip().split(':')
    return int(parts[0]) * 60 + int(parts[1])


def _format_hm(total_minutes):
    total_minutes = max(0, int(total_minutes))
    return f'{total_minutes // 60:02d}:{total_minutes % 60:02d}'


def _next_period_number():
    from models import Period

    max_n = db.session.query(db.func.max(Period.number)).scalar()
    return (max_n or 0) + 1


def _count_lessons():
    from sqlalchemy import or_

    from models import Period

    return (
        Period.query.filter_by(is_active=True)
        .filter(or_(Period.period_kind == 'lesson', Period.period_kind.is_(None)))
        .count()
    )


def _ordered_periods():
    from models import Period

    return (
        Period.query.filter_by(is_active=True)
        .order_by(Period.sort_order, Period.number)
        .all()
    )


def _is_lesson(period):
    return (period.period_kind or 'lesson') != 'break'


STANDARD_BREAK_AFTER = [2, 4, 6, 8]


def _break_for_after_lesson(after_lesson_n):
    from models import Period

    return (
        Period.query.filter_by(
            is_active=True, period_kind='break', after_lesson=after_lesson_n
        )
        .first()
    )


def _anchor_lesson(after_lesson_n):
    lesson_count = 0
    for p in _ordered_periods():
        if _is_lesson(p):
            lesson_count += 1
            if lesson_count == after_lesson_n:
                return p
    return None


def _delete_period_and_compact_sort(period):
    from models import Period

    deleted_sort = period.sort_order
    db.session.delete(period)
    db.session.flush()
    for other in Period.query.filter(Period.sort_order > deleted_sort).all():
        other.sort_order -= 1


def _insert_break_after_lesson(after_lesson_n, start_time, end_time, name='Große Pause'):
    """Fügt eine Pause nach der N-ten Unterrichtsstunde ein (sort_order + interne Nr. automatisch)."""
    from models import Period

    ordered = _ordered_periods()
    lesson_count = 0
    anchor = None

    for p in ordered:
        if _is_lesson(p):
            lesson_count += 1
            if lesson_count == after_lesson_n:
                anchor = p
                break

    if anchor is None:
        return False, f'Es gibt keine {after_lesson_n}. Unterrichtsstunde im Stundenplan.'

    pos = ordered.index(anchor)
    if pos + 1 < len(ordered):
        nxt = ordered[pos + 1]
        if not _is_lesson(nxt) and (nxt.after_lesson == after_lesson_n or nxt.after_lesson is None):
            return False, f'Nach der {after_lesson_n}. Stunde ist bereits eine Pause eingetragen.'

    insert_sort = anchor.sort_order + 1
    for p in Period.query.filter(Period.sort_order >= insert_sort).all():
        p.sort_order += 1

    new_p = Period(
        number=_next_period_number(),
        name=name.strip() or 'Große Pause',
        start_time=start_time,
        end_time=end_time,
        sort_order=insert_sort,
        is_active=True,
        period_kind='break',
        after_lesson=after_lesson_n,
    )
    db.session.add(new_p)
    return True, None


# ─── Stunden (Periods) ────────────────────────────────────────────────────────

@admin_dyn_bp.route('/periods')
def periods():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    from models import Period, PeriodTemplate, Room, RoomPeriod
    
    room_id = request.args.get('room_id', default=0, type=int)
    rooms = Room.query.order_by(Room.sort_order, Room.name).all()
    
    if room_id > 0:
        room = Room.query.get_or_404(room_id)
        if room.use_custom_schedule:
            all_periods = RoomPeriod.query.filter_by(room_id=room_id).order_by(RoomPeriod.sort_order, RoomPeriod.period_number).all()
        else:
            all_periods = []
        next_num = 1
        if all_periods:
            lessons = [p for p in all_periods if p.period_kind == 'lesson']
            next_num = max([p.period_number for p in lessons]) + 1 if lessons else 1
    else:
        room = None
        all_periods = Period.query.order_by(Period.sort_order, Period.number).all()
        next_num = _next_period_number()
        
    saved_templates = PeriodTemplate.query.order_by(PeriodTemplate.created_at.desc()).all()
    lesson_count = sum(1 for p in all_periods if p.is_active and _is_lesson(p))
    break_after_lessons = {
        p.after_lesson
        for p in all_periods
        if p.is_active and getattr(p, 'period_kind', 'lesson') == 'break' and p.after_lesson
    }
    return render_template(
        'admin_periods.html',
        room_id=room_id,
        rooms=rooms,
        room=room,
        periods=all_periods,
        saved_templates=saved_templates,
        builtin_templates=_BUILTIN_TEMPLATES,
        lesson_count=lesson_count,
        break_after_lessons=break_after_lessons,
        next_period_number=next_num,
    )


@admin_dyn_bp.route('/periods/add', methods=['POST'])
def periods_add():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    from models import Period
    try:
        number = int(request.form.get('number', 0))
        name = request.form.get('name', '').strip()
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()

        if not name or not start_time or not end_time or number < 1:
            flash('Bitte alle Pflichtfelder ausfüllen.', 'error')
            return redirect(url_for('admin_dyn.periods'))

        if Period.query.filter_by(number=number).first():
            flash(f'Stunde {number} existiert bereits.', 'error')
            return redirect(url_for('admin_dyn.periods'))

        period_kind = request.form.get('period_kind', 'lesson')
        if period_kind not in ('lesson', 'break'):
            period_kind = 'lesson'

        max_sort = db.session.query(db.func.max(Period.sort_order)).scalar() or 0
        p = Period(
            number=number,
            name=name,
            start_time=start_time,
            end_time=end_time,
            sort_order=max_sort + 1,
            is_active=True,
            period_kind=period_kind,
        )
        db.session.add(p)
        db.session.commit()
        _after_periods_changed()
        kind_label = 'Große Pause' if period_kind == 'break' else 'Stunde'
        flash(f'{kind_label} {number} ({name}) hinzugefügt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/insert-break', methods=['POST'])
def periods_insert_break():
    """Große Pause nach einer Unterrichtsstunde einfügen (ohne manuelle Slot-Nr.)."""
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    try:
        after_lesson = int(request.form.get('after_lesson', 0))
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        name = request.form.get('name', 'Große Pause').strip()

        if after_lesson < 1:
            flash('Bitte wählen Sie, nach welcher Unterrichtsstunde die Pause kommt.', 'error')
            return redirect(url_for('admin_dyn.periods'))

        if not start_time or not end_time:
            from models import Period

            ordered = _ordered_periods()
            lesson_count = 0
            anchor = None
            for p in ordered:
                if _is_lesson(p):
                    lesson_count += 1
                    if lesson_count == after_lesson:
                        anchor = p
                        break
            if anchor:
                start_time = anchor.end_time
                duration = int(request.form.get('pause_minutes', 20) or 20)
                end_time = _format_hm(_parse_hm(start_time) + duration)
            else:
                flash('Zeiten konnten nicht ermittelt werden – bitte Beginn und Ende angeben.', 'error')
                return redirect(url_for('admin_dyn.periods'))

        ok, err = _insert_break_after_lesson(after_lesson, start_time, end_time, name)
        if ok:
            db.session.commit()
            _after_periods_changed()
            flash(
                f'Große Pause nach der {after_lesson}. Stunde eingefügt ({start_time}–{end_time}).',
                'success',
            )
        else:
            db.session.rollback()
            flash(err or 'Pause konnte nicht eingefügt werden.', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/setup-standard-breaks', methods=['POST'])
def periods_setup_standard_breaks():
    """Große Pausen nach 2./4./6./8. Stunde anlegen oder entfernen (Checkboxen speichern)."""
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    try:
        pause_minutes = int(request.form.get('pause_minutes', 20) or 20)
        pause_minutes = max(5, min(90, pause_minutes))
        lesson_count = _count_lessons()
        allowed = {n for n in STANDARD_BREAK_AFTER if n <= lesson_count}
        selected = {
            n for n in request.form.getlist('after_lesson', type=int) if n in allowed
        }

        added = 0
        removed = 0
        skipped = []

        for after_n in sorted(allowed):
            existing = _break_for_after_lesson(after_n)
            if after_n not in selected:
                if existing:
                    _delete_period_and_compact_sort(existing)
                    removed += 1
                continue
            if existing:
                continue
            anchor = _anchor_lesson(after_n)
            if not anchor:
                skipped.append(str(after_n))
                continue
            start_time = anchor.end_time
            end_time = _format_hm(_parse_hm(start_time) + pause_minutes)
            ok, err = _insert_break_after_lesson(after_n, start_time, end_time)
            if ok:
                added += 1
            elif err:
                skipped.append(f'{after_n}. ({err})')

        db.session.commit()
        _after_periods_changed()
        parts = []
        if added:
            parts.append(f'{added} Pause(n) angelegt')
        if removed:
            parts.append(f'{removed} Pause(n) entfernt')
        msg = (', '.join(parts) + '.') if parts else 'Keine Änderungen an den Pausen.'
        if skipped:
            msg += f' Übersprungen: {", ".join(skipped)}.'
        flash(msg, 'success' if (added or removed) else 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/<int:period_id>/edit', methods=['POST'])
def periods_edit(period_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    from models import Period
    p = Period.query.get_or_404(period_id)
    try:
        p.name = request.form.get('name', p.name).strip()
        p.start_time = request.form.get('start_time', p.start_time).strip()
        p.end_time = request.form.get('end_time', p.end_time).strip()
        p.is_active = request.form.get('is_active') == '1'
        period_kind = request.form.get('period_kind', p.period_kind or 'lesson')
        p.period_kind = period_kind if period_kind in ('lesson', 'break') else 'lesson'
        if p.period_kind == 'break':
            raw_after = request.form.get('after_lesson', '').strip()
            p.after_lesson = int(raw_after) if raw_after else p.after_lesson
        else:
            p.after_lesson = None
        db.session.commit()
        _after_periods_changed()
        flash('Zeitfenster aktualisiert.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/<int:period_id>/delete', methods=['POST'])
def periods_delete(period_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    from models import Period
    p = Period.query.get_or_404(period_id)
    try:
        num = p.number
        _delete_period_and_compact_sort(p)
        db.session.commit()
        _after_periods_changed()
        flash(f'Zeitfenster {num} gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.periods'))


# ─── Stunden-Vorlagen ─────────────────────────────────────────────────────────

@admin_dyn_bp.route('/periods/templates/save', methods=['POST'])
def periods_templates_save():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('admin_dyn.periods'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    from models import Period, PeriodTemplate
    template_name = request.form.get('template_name', '').strip()
    template_desc = request.form.get('template_desc', '').strip()

    if not template_name:
        flash('Bitte einen Namen für die Vorlage eingeben.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    periods = Period.query.order_by(Period.sort_order, Period.number).all()
    if not periods:
        flash('Keine Stunden vorhanden – Vorlage kann nicht gespeichert werden.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    periods_data = [
        {
            'number': p.number,
            'name': p.name,
            'start': p.start_time,
            'end': p.end_time,
            'kind': p.period_kind or 'lesson',
            'after_lesson': p.after_lesson,
        }
        for p in periods
    ]

    try:
        tmpl = PeriodTemplate(
            name=template_name,
            description=template_desc or None,
            periods_json=_json.dumps(periods_data, ensure_ascii=False),
        )
        db.session.add(tmpl)
        db.session.commit()
        flash(f'Vorlage „{template_name}" gespeichert ({len(periods_data)} Stunden).', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Speichern: {e}', 'error')

    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/templates/<int:tmpl_id>/load', methods=['POST'])
def periods_templates_load(tmpl_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('admin_dyn.periods'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    from models import Period, PeriodTemplate
    tmpl = PeriodTemplate.query.get_or_404(tmpl_id)
    _apply_period_template(tmpl.get_periods(), tmpl.name)
    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/templates/load-builtin', methods=['POST'])
def periods_templates_load_builtin():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('admin_dyn.periods'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    builtin_id = request.form.get('builtin_id', '')
    tmpl = next((t for t in _BUILTIN_TEMPLATES if t['id'] == builtin_id), None)
    if not tmpl:
        flash('Vorlage nicht gefunden.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    _apply_period_template(tmpl['periods'], tmpl['name'])
    return redirect(url_for('admin_dyn.periods'))


@admin_dyn_bp.route('/periods/templates/<int:tmpl_id>/delete', methods=['POST'])
def periods_templates_delete(tmpl_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('admin_dyn.periods'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods'))

    from models import PeriodTemplate
    tmpl = PeriodTemplate.query.get_or_404(tmpl_id)
    name = tmpl.name
    try:
        db.session.delete(tmpl)
        db.session.commit()
        flash(f'Vorlage „{name}" gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.periods'))


def _apply_period_template(periods_data, name):
    """Ersetzt alle aktuellen Stunden durch die Vorlage."""
    from models import Period
    try:
        Period.query.delete()
        for idx, p in enumerate(periods_data):
            period = Period(
                number=p['number'],
                name=p['name'],
                start_time=p['start'],
                end_time=p['end'],
                sort_order=idx + 1,
                is_active=True,
                period_kind=p.get('kind', 'lesson'),
                after_lesson=p.get('after_lesson'),
            )
            db.session.add(period)
        db.session.commit()
        _after_periods_changed()
        flash(f'Vorlage „{name}" geladen – {len(periods_data)} Stunden übernommen.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Laden der Vorlage: {e}', 'error')


# ─── Kurse (Courses) ──────────────────────────────────────────────────────────

@admin_dyn_bp.route('/courses')
def courses():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    from models import Course, Period, Room, RoomPeriod, RoomCourse
    
    room_id = request.args.get('room_id', default=0, type=int)
    rooms = Room.query.order_by(Room.sort_order, Room.name).all()
    
    weekdays = [('Mon', 'Montag'), ('Tue', 'Dienstag'), ('Wed', 'Mittwoch'), ('Thu', 'Donnerstag'), ('Fri', 'Freitag')]
    
    if room_id > 0:
        room = Room.query.get_or_404(room_id)
        all_courses = Course.query.filter_by(room_id=room_id).order_by(Course.course_type.desc(), Course.weekday, Course.period_number, Course.sort_order).all()
        if room.use_custom_schedule:
            periods = RoomPeriod.query.filter_by(room_id=room_id).order_by(RoomPeriod.sort_order, RoomPeriod.period_number).all()
            custom_courses_list = RoomCourse.query.filter_by(room_id=room_id).all()
            room_courses = {wd: {} for wd in ("Mon", "Tue", "Wed", "Thu", "Fri")}
            for rc in custom_courses_list:
                room_courses.setdefault(rc.weekday, {})[rc.period_number] = rc.course_id
        else:
            periods = []
            room_courses = {}
    else:
        room = None
        all_courses = Course.query.filter_by(room_id=None).order_by(Course.course_type.desc(), Course.weekday, Course.period_number, Course.sort_order).all()
        periods = []
        room_courses = {}
        
    all_periods = (
        Period.query.filter_by(is_active=True)
        .order_by(Period.sort_order, Period.number)
        .all()
    )
    
    return render_template(
        'admin_courses.html',
        room_id=room_id,
        rooms=rooms,
        room=room,
        courses=all_courses,
        periods=periods,
        global_periods=all_periods,
        room_courses=room_courses,
        weekdays=weekdays,
        csrf_token=session.get('csrf_token')
    )


@admin_dyn_bp.route('/courses/add', methods=['POST'])
def courses_add():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    room_id = request.form.get('room_id', default=0, type=int)
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses', room_id=room_id))

    from models import Course
    try:
        name = request.form.get('name', '').strip()
        course_type = request.form.get('course_type', 'free')
        weekday = request.form.get('weekday', '').strip() or None
        period_number_raw = request.form.get('period_number', '').strip()
        period_number = int(period_number_raw) if period_number_raw else None
        color = request.form.get('color', '#E91E63').strip()
        icon = request.form.get('icon', '').strip() or None

        if not name:
            flash('Bitte einen Namen eingeben.', 'error')
            return redirect(url_for('admin_dyn.courses', room_id=room_id))

        if course_type == 'fixed' and (not weekday or period_number is None):
            flash('Für feste Kurse bitte Wochentag und Stunde angeben.', 'error')
            return redirect(url_for('admin_dyn.courses', room_id=room_id))

        if course_type == 'fixed' and period_number is not None:
            from dynamic_config import is_break_period
            if is_break_period(period_number, room_id=room_id if room_id > 0 else None):
                flash('Feste Kurse können nicht in großen Pausen gebucht werden.', 'error')
                return redirect(url_for('admin_dyn.courses', room_id=room_id))

        max_order = db.session.query(db.func.max(Course.sort_order)).scalar() or 0
        c = Course(
            name=name,
            course_type=course_type,
            weekday=weekday if course_type == 'fixed' else None,
            period_number=period_number if course_type == 'fixed' else None,
            color=color,
            icon=icon,
            is_active=True,
            sort_order=max_order + 1,
            room_id=room_id if room_id > 0 else None
        )
        db.session.add(c)
        db.session.commit()
        flash(f'Kurs „{name}" hinzugefügt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.courses', room_id=room_id))


@admin_dyn_bp.route('/courses/<int:course_id>/edit', methods=['POST'])
def courses_edit(course_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    room_id = request.form.get('room_id', default=0, type=int)
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses', room_id=room_id))

    from models import Course
    c = Course.query.get_or_404(course_id)
    try:
        c.name = request.form.get('name', c.name).strip()
        c.course_type = request.form.get('course_type', c.course_type)
        weekday = request.form.get('weekday', '').strip()
        period_number_raw = request.form.get('period_number', '').strip()
        c.weekday = weekday if c.course_type == 'fixed' else None
        c.period_number = int(period_number_raw) if (c.course_type == 'fixed' and period_number_raw) else None
        c.color = request.form.get('color', c.color).strip()
        icon = request.form.get('icon', '').strip()
        c.icon = icon or None
        c.is_active = request.form.get('is_active') == '1'
        db.session.commit()
        flash(f'Kurs „{c.name}" aktualisiert.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.courses', room_id=room_id))


@admin_dyn_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
def courses_delete(course_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    
    from models import Course
    c = Course.query.get_or_404(course_id)
    room_id = c.room_id or 0
    
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses', room_id=room_id))

    try:
        name = c.name
        db.session.delete(c)
        db.session.commit()
        flash(f'Kurs „{name}" gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.courses', room_id=room_id))


# ─── Schulklassen ─────────────────────────────────────────────────────────────

@admin_dyn_bp.route('/classes')
def classes():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    from models import SchoolClass
    all_classes = SchoolClass.query.order_by(SchoolClass.sort_order, SchoolClass.name).all()
    return render_template('admin_classes.html', classes=all_classes)


@admin_dyn_bp.route('/classes/add', methods=['POST'])
def classes_add():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.classes'))

    from models import SchoolClass
    try:
        name = request.form.get('name', '').strip()
        if not name:
            flash('Bitte einen Klassennamen eingeben.', 'error')
            return redirect(url_for('admin_dyn.classes'))
        if SchoolClass.query.filter_by(name=name).first():
            flash(f'Klasse „{name}" existiert bereits.', 'error')
            return redirect(url_for('admin_dyn.classes'))
        max_order = db.session.query(db.func.max(SchoolClass.sort_order)).scalar() or 0
        sc = SchoolClass(name=name, sort_order=max_order + 1, is_active=True)
        db.session.add(sc)
        db.session.commit()
        flash(f'Klasse „{name}" hinzugefügt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.classes'))


@admin_dyn_bp.route('/classes/<int:class_id>/edit', methods=['POST'])
def classes_edit(class_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.classes'))

    from models import SchoolClass
    sc = SchoolClass.query.get_or_404(class_id)
    try:
        sc.name = request.form.get('name', sc.name).strip()
        sc.is_active = request.form.get('is_active') == '1'
        db.session.commit()
        flash(f'Klasse „{sc.name}" aktualisiert.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.classes'))


@admin_dyn_bp.route('/classes/<int:class_id>/delete', methods=['POST'])
def classes_delete(class_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.classes'))

    from models import SchoolClass
    sc = SchoolClass.query.get_or_404(class_id)
    try:
        name = sc.name
        db.session.delete(sc)
        db.session.commit()
        flash(f'Klasse „{name}" gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.classes'))


# ─── Datenbank-Einstellungen ─────────────────────────────────────────────────

@admin_dyn_bp.route('/database-settings', methods=['GET', 'POST'])
def database_settings():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))

    from local_config import get_local, set_database_url
    import sqlalchemy

    test_result = None

    if request.method == 'POST':
        if not _validate_csrf(request.form.get('csrf_token', '')):
            flash('Ungültiges Sicherheits-Token.', 'error')
            return redirect(url_for('admin_dyn.database_settings'))

        action = request.form.get('action', 'save')

        if action == 'test':
            db_url = request.form.get('database_url', '').strip()
            if not db_url:
                test_result = {'success': False, 'message': 'Bitte eine Datenbank-URL eingeben.'}
            else:
                try:
                    engine = sqlalchemy.create_engine(db_url, connect_args={'connect_timeout': 8})
                    with engine.connect() as conn:
                        conn.execute(sqlalchemy.text('SELECT 1'))
                    engine.dispose()
                    test_result = {'success': True, 'message': 'Verbindung erfolgreich! Datenbank ist erreichbar.'}
                except Exception as e:
                    test_result = {'success': False, 'message': f'Verbindung fehlgeschlagen: {e}'}
        else:
            db_url = request.form.get('database_url', '').strip()
            if not db_url:
                flash('Bitte eine Datenbank-URL eingeben.', 'error')
            else:
                set_database_url(db_url)
                from app import _trigger_restart
                _trigger_restart()
                return redirect(url_for('setup.restart_wait'))

    raw_url = get_local('database_url', '')
    if raw_url:
        try:
            from urllib.parse import urlparse
            p = urlparse(raw_url)
            db_url_masked = f"{p.scheme}://***@{p.hostname}{p.path}"
        except Exception:
            db_url_masked = '(konfiguriert)'
    else:
        db_url_masked = ''

    return render_template('admin_db_settings.html',
                           db_configured=bool(raw_url),
                           db_url_masked=db_url_masked,
                           test_result=test_result)


# ─── Buchungs-Einstellungen ───────────────────────────────────────────────────

@admin_dyn_bp.route('/booking-settings', methods=['GET', 'POST'])
def booking_settings():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))

    from system_config import get_config, set_config

    if request.method == 'POST':
        if not _validate_csrf(request.form.get('csrf_token', '')):
            flash('Ungültiges Sicherheits-Token.', 'error')
            return redirect(url_for('admin_dyn.booking_settings'))
        try:
            max_students = int(request.form.get('max_students', 5))
            advance_minutes = int(request.form.get('advance_minutes', 60))
            if max_students < 1 or max_students > 20:
                raise ValueError('Schüleranzahl muss zwischen 1 und 20 liegen.')
            if advance_minutes < 0 or advance_minutes > 1440:
                raise ValueError('Vorlaufzeit muss zwischen 0 und 1440 Minuten liegen.')
            set_config('max_students_per_period', str(max_students), category='booking')
            set_config('booking_advance_minutes', str(advance_minutes), category='booking')
            flash('Buchungs-Einstellungen gespeichert.', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'Fehler: {e}', 'error')
        return redirect(url_for('admin_dyn.booking_settings'))

    max_students = get_config('max_students_per_period') or '5'
    advance_minutes = get_config('booking_advance_minutes') or '60'
    return render_template('admin_booking_settings.html',
                           max_students=int(max_students),
                           advance_minutes=int(advance_minutes))


# ─── Räume (Rooms) ───────────────────────────────────────────────────────────

@admin_dyn_bp.route('/rooms')
def rooms():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    from models import Room
    all_rooms = Room.query.order_by(Room.sort_order, Room.name).all()
    return render_template('admin_rooms.html', rooms=all_rooms)


@admin_dyn_bp.route('/rooms/add', methods=['POST'])
def rooms_add():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.rooms'))

    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        color = request.form.get('color', '#6366f1').strip()
        icon = request.form.get('icon', '🏫').strip()
        max_students_raw = request.form.get('max_students', '').strip()
        max_students = int(max_students_raw) if max_students_raw else None
        sort_order = int(request.form.get('sort_order', 0) or 0)

        if not name:
            flash('Bitte einen Raumnamen eingeben.', 'error')
            return redirect(url_for('admin_dyn.rooms'))

        from models import Room
        if Room.query.filter_by(name=name).first():
            flash(f'Raum „{name}" existiert bereits.', 'error')
            return redirect(url_for('admin_dyn.rooms'))

        from models import create_room
        create_room(name, description, color, icon, max_students, sort_order)
        flash(f'Raum „{name}" hinzugefügt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.rooms'))


@admin_dyn_bp.route('/rooms/<int:room_id>/edit', methods=['POST'])
def rooms_edit(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.rooms'))

    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        color = request.form.get('color', '#6366f1').strip()
        icon = request.form.get('icon', '🏫').strip()
        max_students_raw = request.form.get('max_students', '').strip()
        max_students = int(max_students_raw) if max_students_raw else None
        sort_order = int(request.form.get('sort_order', 0) or 0)
        is_active = request.form.get('is_active') == '1'

        if not name:
            flash('Bitte einen Raumnamen eingeben.', 'error')
            return redirect(url_for('admin_dyn.rooms'))

        from models import update_room
        update_room(room_id, name=name, description=description, color=color, icon=icon, max_students=max_students, sort_order=sort_order, is_active=is_active)
        flash(f'Raum „{name}" aktualisiert.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.rooms'))


@admin_dyn_bp.route('/rooms/<int:room_id>/delete', methods=['POST'])
def rooms_delete(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.rooms'))

    from models import delete_room, get_room_by_id
    room = get_room_by_id(room_id)
    if not room:
        flash('Raum nicht gefunden.', 'error')
        return redirect(url_for('admin_dyn.rooms'))

    name = room.name
    if delete_room(room_id):
        flash(f'Raum „{name}" gelöscht.', 'success')
    else:
        flash(f'Raum „{name}" konnte nicht gelöscht werden. (Prüfen Sie, ob noch Buchungen darauf laufen).', 'error')
    return redirect(url_for('admin_dyn.rooms'))


# ─── Raumspezifischer Stundenplan (Room-specific Schedule) ────────────────────────

@admin_dyn_bp.route('/rooms/<int:room_id>/schedule', methods=['GET'])
def room_schedule(room_id):
    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/toggle', methods=['POST'])
def room_schedule_toggle(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    from models import Room, RoomPeriod, RoomCourse, copy_global_schedule_to_room, copy_global_courses_to_room
    room = Room.query.get_or_404(room_id)
    
    use_custom = request.form.get('use_custom_schedule') == '1'
    
    try:
        if use_custom:
            room.use_custom_schedule = True
            copy_global_schedule_to_room(room_id)
            copy_global_courses_to_room(room_id)
            db.session.commit()
            flash('Raumspezifischer Stundenplan wurde aktiviert und der globale Plan kopiert.', 'success')
        else:
            room.use_custom_schedule = False
            RoomPeriod.query.filter_by(room_id=room_id).delete()
            RoomCourse.query.filter_by(room_id=room_id).delete()
            db.session.commit()
            flash('Raumspezifischer Stundenplan wurde deaktiviert. Der Raum nutzt wieder den globalen Plan.', 'success')
        _after_periods_changed()
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Umschalten des Stundenplans: {e}', 'error')
        
    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/load-builtin', methods=['POST'])
def room_schedule_load_builtin(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))

    from models import Room, RoomPeriod
    room = Room.query.get_or_404(room_id)
    if not room.use_custom_schedule:
        flash('Der raumspezifische Stundenplan ist nicht aktiv.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))

    builtin_id = request.form.get('builtin_id', '')
    tmpl = next((t for t in _BUILTIN_TEMPLATES if t['id'] == builtin_id), None)
    if not tmpl:
        flash('Vorlage nicht gefunden.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))

    try:
        RoomPeriod.query.filter_by(room_id=room_id).delete()
        for idx, p in enumerate(tmpl['periods']):
            rp = RoomPeriod(
                room_id=room_id,
                period_number=p['number'],
                name=p['name'],
                start_time=p['start'],
                end_time=p['end'],
                sort_order=idx + 1,
                is_active=True,
                period_kind=p.get('kind', 'lesson'),
                after_lesson=p.get('after_lesson'),
            )
            db.session.add(rp)
        db.session.commit()
        _after_periods_changed()
        flash(f'Vorlage „{tmpl["name"]}" geladen – {len(tmpl["periods"])} Stunden übernommen.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Laden der Vorlage: {e}', 'error')

    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/copy_global', methods=['POST'])
def room_schedule_copy_global(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    from models import Room, copy_global_schedule_to_room, copy_global_courses_to_room
    room = Room.query.get_or_404(room_id)
    if not room.use_custom_schedule:
        flash('Der raumspezifische Stundenplan ist nicht aktiv.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    try:
        copy_global_schedule_to_room(room_id)
        copy_global_courses_to_room(room_id)
        db.session.commit()
        flash('Der globale Stundenplan wurde erfolgreich in den Raum kopiert (alle bisherigen Raum-Einstellungen wurden überschrieben).', 'success')
        _after_periods_changed()
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Kopieren des globalen Stundenplans: {e}', 'error')
        
    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/period/add', methods=['POST'])
def room_schedule_period_add(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    from models import Room, RoomPeriod
    room = Room.query.get_or_404(room_id)
    if not room.use_custom_schedule:
        flash('Der raumspezifische Stundenplan ist nicht aktiv.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    try:
        number = int(request.form.get('number', 0))
        name = request.form.get('name', '').strip()
        start = request.form.get('start', '').strip()
        end = request.form.get('end', '').strip()
        kind = request.form.get('kind', 'lesson')
        after_lesson_val = request.form.get('after_lesson')
        after_lesson = int(after_lesson_val) if (kind == 'break' and after_lesson_val) else None
        sort_order = int(request.form.get('sort_order', 0))
        
        if number <= 0:
            flash('Ungültige Periodennummer.', 'error')
            return redirect(url_for('admin_dyn.periods', room_id=room_id))
            
        if not name or not start or not end:
            flash('Bitte füllen Sie Name, Startzeit und Endzeit aus.', 'error')
            return redirect(url_for('admin_dyn.periods', room_id=room_id))
            
        # Prüfen auf Duplikate
        if RoomPeriod.query.filter_by(room_id=room_id, period_number=number).first():
            flash(f'Eine Periode mit der Nummer {number} existiert bereits für diesen Raum.', 'error')
            return redirect(url_for('admin_dyn.periods', room_id=room_id))
            
        rp = RoomPeriod(
            room_id=room_id,
            period_number=number,
            name=name,
            start_time=start,
            end_time=end,
            sort_order=sort_order,
            is_active=True,
            period_kind=kind,
            after_lesson=after_lesson
        )
        db.session.add(rp)
        db.session.commit()
        flash(f'Periode „{name}" hinzugefügt.', 'success')
        _after_periods_changed()
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Hinzufügen der Periode: {e}', 'error')
        
    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/period/<int:period_id>/edit', methods=['POST'])
def room_schedule_period_edit(room_id, period_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    from models import Room, RoomPeriod
    room = Room.query.get_or_404(room_id)
    rp = RoomPeriod.query.filter_by(id=period_id, room_id=room_id).first_or_404()
    
    try:
        number = int(request.form.get('number', 0))
        name = request.form.get('name', '').strip()
        start = request.form.get('start', '').strip()
        end = request.form.get('end', '').strip()
        kind = request.form.get('kind', 'lesson')
        after_lesson_val = request.form.get('after_lesson')
        after_lesson = int(after_lesson_val) if (kind == 'break' and after_lesson_val) else None
        sort_order = int(request.form.get('sort_order', 0))
        is_active = request.form.get('is_active') == '1'
        
        if number <= 0:
            flash('Ungültige Periodennummer.', 'error')
            return redirect(url_for('admin_dyn.periods', room_id=room_id))
            
        if not name or not start or not end:
            flash('Bitte füllen Sie Name, Startzeit und Endzeit aus.', 'error')
            return redirect(url_for('admin_dyn.periods', room_id=room_id))
            
        # Prüfen auf Duplikate bei anderer ID
        dup = RoomPeriod.query.filter_by(room_id=room_id, period_number=number).first()
        if dup and dup.id != period_id:
            flash(f'Eine Periode mit der Nummer {number} existiert bereits.', 'error')
            return redirect(url_for('admin_dyn.periods', room_id=room_id))
            
        rp.period_number = number
        rp.name = name
        rp.start_time = start
        rp.end_time = end
        rp.period_kind = kind
        rp.after_lesson = after_lesson
        rp.sort_order = sort_order
        rp.is_active = is_active
        
        db.session.commit()
        flash(f'Periode „{name}" aktualisiert.', 'success')
        _after_periods_changed()
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Aktualisieren der Periode: {e}', 'error')
        
    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/period/<int:period_id>/delete', methods=['POST'])
def room_schedule_period_delete(room_id, period_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.periods', room_id=room_id))
        
    from models import Room, RoomPeriod
    room = Room.query.get_or_404(room_id)
    rp = RoomPeriod.query.filter_by(id=period_id, room_id=room_id).first_or_404()
    
    try:
        name = rp.name
        db.session.delete(rp)
        db.session.commit()
        flash(f'Periode „{name}" gelöscht.', 'success')
        _after_periods_changed()
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Löschen der Periode: {e}', 'error')
        
    return redirect(url_for('admin_dyn.periods', room_id=room_id))


@admin_dyn_bp.route('/rooms/<int:room_id>/schedule/courses/save', methods=['POST'])
def room_schedule_courses_save(room_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses', room_id=room_id))
        
    from models import Room, RoomCourse, RoomPeriod
    room = Room.query.get_or_404(room_id)
    if not room.use_custom_schedule:
        flash('Der raumspezifische Stundenplan ist nicht aktiv.', 'error')
        return redirect(url_for('admin_dyn.courses', room_id=room_id))
        
    try:
        # Alle bestehenden Kurszuordnungen für diesen Raum löschen
        RoomCourse.query.filter_by(room_id=room_id).delete()
        
        # Alle custom Stunden holen (nur lesson-Periods, breaks brauchen keine Zuweisungen)
        periods = RoomPeriod.query.filter_by(room_id=room_id, period_kind='lesson', is_active=True).all()
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        
        for p in periods:
            for wd in weekdays:
                # Feldname im Formular: course_{weekday}_{period_number}
                form_key = f"course_{wd}_{p.period_number}"
                val = request.form.get(form_key, '').strip()
                if val:
                    try:
                        course_id = int(val)
                        rc = RoomCourse(
                            room_id=room_id,
                            course_id=course_id,
                            weekday=wd,
                            period_number=p.period_number
                        )
                        db.session.add(rc)
                    except ValueError:
                        pass
        db.session.commit()
        flash('Kurs-Zuordnungen für diesen Raum erfolgreich gespeichert.', 'success')
        _after_periods_changed()
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Speichern der Kurs-Zuordnungen: {e}', 'error')
        
    return redirect(url_for('admin_dyn.courses', room_id=room_id))

