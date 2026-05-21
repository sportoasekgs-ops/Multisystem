"""
Setup-Wizard Blueprint für die Erstkonfiguration des Systems.
Schritt-für-Schritt-Einrichtung: Allgemeines → Branding → SMTP → IServ → Fertig
"""

import os
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from system_config import get_config, set_config, set_configs, is_setup_complete, get_branding

setup_bp = Blueprint('setup', __name__, url_prefix='/setup')

STEPS = [
    {'id': 'welcome',  'title': 'Willkommen',        'icon': '👋'},
    {'id': 'general',  'title': 'Allgemeine Daten',   'icon': '🏫'},
    {'id': 'branding', 'title': 'Design & Branding',  'icon': '🎨'},
    {'id': 'smtp',     'title': 'E-Mail / SMTP',      'icon': '📧'},
    {'id': 'iserv',    'title': 'IServ OAuth',         'icon': '🔐'},
    {'id': 'complete', 'title': 'Abgeschlossen',       'icon': '✅'},
]

STEP_IDS = [s['id'] for s in STEPS]


def get_step_index(step_id):
    try:
        return STEP_IDS.index(step_id)
    except ValueError:
        return 0


def step_context(current_step_id):
    idx = get_step_index(current_step_id)
    return {
        'steps': STEPS,
        'current_step': current_step_id,
        'current_step_index': idx,
        'total_steps': len(STEPS),
        'progress_pct': int((idx / (len(STEPS) - 1)) * 100),
        'prev_step': STEP_IDS[idx - 1] if idx > 0 else None,
        'next_step': STEP_IDS[idx + 1] if idx < len(STEPS) - 1 else None,
    }


# ─── Startseite des Wizards ─────────────────────────────────────────────────

@setup_bp.route('/')
def index():
    return redirect(url_for('setup.step', step_id='welcome'))


@setup_bp.route('/<step_id>', methods=['GET', 'POST'])
def step(step_id):
    if step_id not in STEP_IDS:
        return redirect(url_for('setup.step', step_id='welcome'))

    # Wenn Setup bereits fertig, nur Admin darf zurückkehren
    if is_setup_complete() and step_id != 'complete':
        user_role = session.get('user_role')
        if user_role != 'admin':
            return redirect(url_for('dashboard'))

    if request.method == 'POST':
        return _handle_post(step_id)

    ctx = step_context(step_id)
    config = _get_step_config(step_id)
    return render_template(f'setup/{step_id}.html', **ctx, **config)


def _handle_post(step_id):
    """Verarbeitet POST-Requests für jeden Wizard-Schritt."""

    if step_id == 'welcome':
        return redirect(url_for('setup.step', step_id='general'))

    elif step_id == 'general':
        data = {
            'school_name':     request.form.get('school_name', '').strip(),
            'school_subtitle': request.form.get('school_subtitle', '').strip(),
            'contact_name':    request.form.get('contact_name', '').strip(),
            'contact_email':   request.form.get('contact_email', '').strip(),
            'contact_phone':   request.form.get('contact_phone', '').strip(),
            'school_address':  request.form.get('school_address', '').strip(),
            'imprint_text':    request.form.get('imprint_text', '').strip(),
            'privacy_text':    request.form.get('privacy_text', '').strip(),
        }
        if not data['school_name']:
            flash('Bitte gib einen Schulnamen ein.', 'error')
            return redirect(url_for('setup.step', step_id='general'))
        set_configs(data, category='general')
        flash('Allgemeine Daten gespeichert.', 'success')
        return redirect(url_for('setup.step', step_id='branding'))

    elif step_id == 'branding':
        primary_color   = request.form.get('primary_color', '#E91E63').strip()
        secondary_color = request.form.get('secondary_color', '#C2185B').strip()
        background_color = request.form.get('background_color', '#fce4ec').strip()

        # Logo-Upload
        logo_filename = get_config('logo_filename', 'logo.png')
        if 'logo_file' in request.files:
            f = request.files['logo_file']
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.svg', '.webp'):
                    logo_filename = f'custom_logo{ext}'
                    save_path = os.path.join('static', 'uploads', logo_filename)
                    f.save(save_path)
                else:
                    flash('Logo muss PNG, JPG, SVG oder WebP sein.', 'error')

        # Favicon-Upload
        favicon_filename = get_config('favicon_filename', 'logo.png')
        if 'favicon_file' in request.files:
            f = request.files['favicon_file']
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in ('.png', '.ico', '.svg'):
                    favicon_filename = f'custom_favicon{ext}'
                    save_path = os.path.join('static', 'uploads', favicon_filename)
                    f.save(save_path)

        set_configs({
            'primary_color':    primary_color,
            'secondary_color':  secondary_color,
            'background_color': background_color,
            'logo_filename':    logo_filename,
            'favicon_filename': favicon_filename,
        }, category='branding')
        flash('Design gespeichert.', 'success')
        return redirect(url_for('setup.step', step_id='smtp'))

    elif step_id == 'smtp':
        action = request.form.get('action', 'save')
        if action == 'skip':
            flash('E-Mail-Konfiguration übersprungen.', 'info')
            return redirect(url_for('setup.step', step_id='iserv'))

        data = {
            'smtp_host':  request.form.get('smtp_host', '').strip(),
            'smtp_port':  request.form.get('smtp_port', '587').strip(),
            'smtp_user':  request.form.get('smtp_user', '').strip(),
            'smtp_pass':  request.form.get('smtp_pass', '').strip(),
            'smtp_tls':   request.form.get('smtp_tls', 'starttls').strip(),
            'smtp_from':  request.form.get('smtp_from', '').strip(),
            'admin_email': request.form.get('admin_email', '').strip(),
        }
        set_configs(data, category='smtp')
        flash('E-Mail-Konfiguration gespeichert.', 'success')
        return redirect(url_for('setup.step', step_id='iserv'))

    elif step_id == 'iserv':
        action = request.form.get('action', 'save')
        if action == 'skip':
            flash('IServ-Konfiguration übersprungen. Kann später eingerichtet werden.', 'info')
            return redirect(url_for('setup.step', step_id='complete'))

        iserv_domain        = request.form.get('iserv_domain', '').strip()
        iserv_client_id     = request.form.get('iserv_client_id', '').strip()
        iserv_client_secret = request.form.get('iserv_client_secret', '').strip()
        admin_email         = request.form.get('admin_email', '').strip()

        if not iserv_domain or not iserv_client_id or not iserv_client_secret:
            flash('Bitte fülle alle IServ-Felder aus oder überspringe diesen Schritt.', 'error')
            return redirect(url_for('setup.step', step_id='iserv'))

        set_configs({
            'iserv_domain':        iserv_domain,
            'iserv_client_id':     iserv_client_id,
            'iserv_client_secret': iserv_client_secret,
            'iserv_admin_email':   admin_email,
        }, category='iserv')

        # Auch als Umgebungsvariable im Prozess setzen (wirkt sofort)
        os.environ['ISERV_DOMAIN']        = iserv_domain
        os.environ['ISERV_CLIENT_ID']     = iserv_client_id
        os.environ['ISERV_CLIENT_SECRET'] = iserv_client_secret
        if admin_email:
            os.environ['ADMIN_EMAIL'] = admin_email

        flash('IServ-Konfiguration gespeichert. Bitte starte die App neu, damit OAuth aktiv wird.', 'success')
        return redirect(url_for('setup.step', step_id='complete'))

    elif step_id == 'complete':
        set_config('setup_complete', 'true', category='system')
        flash('Setup abgeschlossen! Willkommen im System.', 'success')
        return redirect(url_for('login'))

    return redirect(url_for('setup.step', step_id=step_id))


def _get_step_config(step_id):
    """Lädt gespeicherte Werte für das aktuelle Formular."""
    if step_id == 'general':
        return {
            'school_name':     get_config('school_name', ''),
            'school_subtitle': get_config('school_subtitle', ''),
            'contact_name':    get_config('contact_name', ''),
            'contact_email':   get_config('contact_email', ''),
            'contact_phone':   get_config('contact_phone', ''),
            'school_address':  get_config('school_address', ''),
            'imprint_text':    get_config('imprint_text', ''),
            'privacy_text':    get_config('privacy_text', ''),
        }
    elif step_id == 'branding':
        return {
            'primary_color':    get_config('primary_color', '#E91E63'),
            'secondary_color':  get_config('secondary_color', '#C2185B'),
            'background_color': get_config('background_color', '#fce4ec'),
            'logo_filename':    get_config('logo_filename', 'logo.png'),
            'favicon_filename': get_config('favicon_filename', 'logo.png'),
        }
    elif step_id == 'smtp':
        return {
            'smtp_host':   get_config('smtp_host', ''),
            'smtp_port':   get_config('smtp_port', '587'),
            'smtp_user':   get_config('smtp_user', ''),
            'smtp_pass':   get_config('smtp_pass', ''),
            'smtp_tls':    get_config('smtp_tls', 'starttls'),
            'smtp_from':   get_config('smtp_from', ''),
            'admin_email': get_config('admin_email', ''),
        }
    elif step_id == 'iserv':
        return {
            'iserv_domain':        get_config('iserv_domain', os.environ.get('ISERV_DOMAIN', '')),
            'iserv_client_id':     get_config('iserv_client_id', os.environ.get('ISERV_CLIENT_ID', '')),
            'iserv_client_secret': get_config('iserv_client_secret', os.environ.get('ISERV_CLIENT_SECRET', '')),
            'iserv_admin_email':   get_config('iserv_admin_email', os.environ.get('ADMIN_EMAIL', '')),
        }
    elif step_id == 'complete':
        return {
            'school_name':     get_config('school_name', 'Ihre Einrichtung'),
            'iserv_domain':    get_config('iserv_domain', ''),
            'smtp_host':       get_config('smtp_host', ''),
            'logo_filename':   get_config('logo_filename', 'logo.png'),
            'primary_color':   get_config('primary_color', '#E91E63'),
        }
    return {}


# ─── AJAX: SMTP-Test ────────────────────────────────────────────────────────

@setup_bp.route('/test-smtp', methods=['POST'])
def test_smtp():
    """Sendet eine Test-E-Mail über die eingegebenen SMTP-Daten."""
    data = request.get_json(silent=True) or {}
    host      = data.get('smtp_host', '').strip()
    port      = int(data.get('smtp_port', 587))
    user      = data.get('smtp_user', '').strip()
    password  = data.get('smtp_pass', '').strip()
    tls_mode  = data.get('smtp_tls', 'starttls')
    recipient = data.get('test_email', user).strip()

    if not host or not user or not password:
        return jsonify({'success': False, 'message': 'Host, Benutzer und Passwort sind erforderlich.'})

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart('alternative')
        msg['Subject'] = '✅ SportOase SMTP-Test erfolgreich'
        msg['From']    = user
        msg['To']      = recipient

        html = """
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:30px;">
            <h2 style="color:#E91E63;">✅ SMTP-Test erfolgreich!</h2>
            <p>Diese E-Mail wurde über deine SMTP-Konfiguration gesendet.</p>
            <p style="color:#666;font-size:13px;">SportOase Setup-Wizard</p>
        </div>"""
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        if tls_mode == 'ssl':
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                server.login(user, password)
                server.sendmail(user, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.ehlo()
                if tls_mode == 'starttls':
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
                server.sendmail(user, [recipient], msg.as_string())

        return jsonify({'success': True, 'message': f'Test-E-Mail erfolgreich an {recipient} gesendet!'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'})


# ─── Setup von Admin erneut aufrufen ────────────────────────────────────────

@setup_bp.route('/reopen')
def reopen():
    """Erlaubt Admin, den Setup-Wizard erneut aufzurufen."""
    if session.get('user_role') != 'admin':
        flash('Nur Admins können den Setup-Wizard erneut aufrufen.', 'error')
        return redirect(url_for('dashboard'))
    return redirect(url_for('setup.step', step_id='general'))
