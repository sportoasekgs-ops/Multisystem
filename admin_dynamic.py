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
            {'number': 1, 'name': '1. Stunde', 'start': '07:50', 'end': '08:35'},
            {'number': 2, 'name': '2. Stunde', 'start': '08:35', 'end': '09:20'},
            {'number': 3, 'name': '3. Stunde', 'start': '09:40', 'end': '10:25'},
            {'number': 4, 'name': '4. Stunde', 'start': '10:25', 'end': '11:10'},
            {'number': 5, 'name': '5. Stunde', 'start': '11:30', 'end': '12:15'},
            {'number': 6, 'name': '6. Stunde', 'start': '12:15', 'end': '13:00'},
        ],
    },
    {
        'id': 'builtin_8',
        'name': 'Ganztagsschule (8 Stunden)',
        'description': 'Ganztag von 7:50–15:10 Uhr mit Mittagspause',
        'periods': [
            {'number': 1, 'name': '1. Stunde', 'start': '07:50', 'end': '08:35'},
            {'number': 2, 'name': '2. Stunde', 'start': '08:35', 'end': '09:20'},
            {'number': 3, 'name': '3. Stunde', 'start': '09:40', 'end': '10:25'},
            {'number': 4, 'name': '4. Stunde', 'start': '10:25', 'end': '11:10'},
            {'number': 5, 'name': '5. Stunde', 'start': '11:30', 'end': '12:15'},
            {'number': 6, 'name': '6. Stunde', 'start': '12:15', 'end': '13:00'},
            {'number': 7, 'name': '7. Stunde', 'start': '14:00', 'end': '14:45'},
            {'number': 8, 'name': '8. Stunde', 'start': '14:45', 'end': '15:30'},
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


# ─── Stunden (Periods) ────────────────────────────────────────────────────────

@admin_dyn_bp.route('/periods')
def periods():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    from models import Period, PeriodTemplate
    all_periods = Period.query.order_by(Period.sort_order, Period.number).all()
    saved_templates = PeriodTemplate.query.order_by(PeriodTemplate.created_at.desc()).all()
    return render_template('admin_periods.html',
                           periods=all_periods,
                           saved_templates=saved_templates,
                           builtin_templates=_BUILTIN_TEMPLATES)


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

        p = Period(
            number=number,
            name=name,
            start_time=start_time,
            end_time=end_time,
            sort_order=number,
            is_active=True,
        )
        db.session.add(p)
        db.session.commit()
        flash(f'Stunde {number} ({name}) hinzugefügt.', 'success')
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
        db.session.commit()
        flash('Stunde aktualisiert.', 'success')
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
        db.session.delete(p)
        db.session.commit()
        flash(f'Stunde {p.number} gelöscht.', 'success')
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

    periods_data = [{'number': p.number, 'name': p.name, 'start': p.start_time, 'end': p.end_time} for p in periods]

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
        for p in periods_data:
            period = Period(
                number=p['number'],
                name=p['name'],
                start_time=p['start'],
                end_time=p['end'],
                sort_order=p['number'],
                is_active=True,
            )
            db.session.add(period)
        db.session.commit()
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
    from models import Course, Period
    all_courses = Course.query.order_by(Course.course_type.desc(), Course.weekday, Course.period_number, Course.sort_order).all()
    all_periods = Period.query.filter_by(is_active=True).order_by(Period.number).all()
    weekdays = [('Mon', 'Montag'), ('Tue', 'Dienstag'), ('Wed', 'Mittwoch'), ('Thu', 'Donnerstag'), ('Fri', 'Freitag')]
    return render_template('admin_courses.html', courses=all_courses, periods=all_periods, weekdays=weekdays)


@admin_dyn_bp.route('/courses/add', methods=['POST'])
def courses_add():
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses'))

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
            return redirect(url_for('admin_dyn.courses'))

        if course_type == 'fixed' and (not weekday or period_number is None):
            flash('Für feste Kurse bitte Wochentag und Stunde angeben.', 'error')
            return redirect(url_for('admin_dyn.courses'))

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
        )
        db.session.add(c)
        db.session.commit()
        flash(f'Kurs „{name}" hinzugefügt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.courses'))


@admin_dyn_bp.route('/courses/<int:course_id>/edit', methods=['POST'])
def courses_edit(course_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses'))

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
    return redirect(url_for('admin_dyn.courses'))


@admin_dyn_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
def courses_delete(course_id):
    if not _admin_required():
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('dashboard'))
    if not _validate_csrf(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_dyn.courses'))

    from models import Course
    c = Course.query.get_or_404(course_id)
    try:
        name = c.name
        db.session.delete(c)
        db.session.commit()
        flash(f'Kurs „{name}" gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'error')
    return redirect(url_for('admin_dyn.courses'))


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
