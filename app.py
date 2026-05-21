# Haupt-Anwendungsdatei für die SportOase-Buchungssystem
# Diese Datei enthält alle Routen (URLs) und die Logik der Webanwendung

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from datetime import datetime, timedelta, date
from werkzeug.middleware.proxy_fix import ProxyFix
import pytz
import json
import os
import queue
import threading

# Flask-App erstellen
app = Flask(__name__)

# Jinja2-Filter: Nachnamen kürzen (Datenschutz)
@app.template_filter('abbreviate_name')
def abbreviate_name_filter(name):
    """Kürzt den Nachnamen auf den ersten Buchstaben + Punkt.
    z.B. 'Max Mustermann' → 'Max M.'
    """
    if not name:
        return name
    parts = name.strip().split()
    if len(parts) <= 1:
        return name
    return parts[0] + ' ' + parts[-1][0] + '.'

# Session-Secret aus Umgebungsvariable (MUSS gesetzt sein!)
session_secret = os.environ.get('SESSION_SECRET')
if not session_secret:
    raise RuntimeError(
        "SESSION_SECRET Umgebungsvariable ist nicht gesetzt! "
        "Bitte setzen Sie einen sicheren, zufälligen Wert in Replit Secrets."
    )
app.secret_key = session_secret
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Cookie-Einstellungen für iFrame-Kompatibilität (IServ Embed)
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

@app.after_request
def add_iframe_headers(response):
    """Erlaubt Einbettung in IServ iFrame"""
    # Erlaube Einbettung von kgs-pattensen.de
    response.headers['X-Frame-Options'] = 'ALLOW-FROM https://kgs-pattensen.de'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self' https://kgs-pattensen.de"
    return response

# SSE Broadcaster für Echtzeit-Benachrichtigungen
notification_subscribers = []
subscribers_lock = threading.Lock()

def broadcast_notification(notification_data):
    """Sendet eine Benachrichtigung an alle verbundenen SSE-Clients"""
    with subscribers_lock:
        dead_queues = []
        for q in notification_subscribers:
            try:
                q.put_nowait(notification_data)
            except queue.Full:
                dead_queues.append(q)
        
        for q in dead_queues:
            notification_subscribers.remove(q)

# CSRF-Token Generierung und Validierung
import secrets

def generate_csrf_token():
    """Generiert ein CSRF-Token und speichert es in der Session"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf_token(token):
    """Validiert das CSRF-Token"""
    return token == session.get('csrf_token')

@app.context_processor
def inject_csrf_token():
    """Macht csrf_token in allen Templates verfügbar"""
    return dict(csrf_token=generate_csrf_token())

# Datenbank-Konfiguration
# Reihenfolge: lokale Datei (sportoase_local.json) → Env-Var DATABASE_URL
from local_config import get_database_url, is_database_configured, set_database_url
db_uri = get_database_url()

# ── Bootstrap-Modus: keine DB-URL vorhanden ──────────────────────────────────
_BOOTSTRAP_MODE = not bool(db_uri)

if _BOOTSTRAP_MODE:
    # Minimale Routen zum Eingeben der Datenbank-URL
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def bootstrap_catch_all(path):
        return redirect(url_for('bootstrap_db'))

    @app.route('/bootstrap', methods=['GET', 'POST'])
    def bootstrap_db():
        error = None
        if request.method == 'POST':
            url = request.form.get('database_url', '').strip()
            if not url:
                error = 'Bitte eine Datenbank-URL eingeben.'
            else:
                set_database_url(url)
                return render_template('bootstrap_saved.html')
        return render_template('bootstrap_db.html', error=error)

else:
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

if not _BOOTSTRAP_MODE:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Importiere zentrale Datenbank-Instanz
from database import db

# Initialisiere SQLAlchemy mit der App (nur wenn DB verfügbar)
if not _BOOTSTRAP_MODE:
    db.init_app(app)

# Importiere Modelle und Hilfsfunktionen (nur wenn DB verfügbar)
if not _BOOTSTRAP_MODE:
    from models import (
        create_user, get_user_by_username, get_user_by_email,
        get_user_by_id, verify_password, get_all_users, create_booking,
        get_bookings_for_date_period, count_students_for_period, get_all_bookings,
        get_bookings_by_date, get_bookings_for_week, get_booking_by_id,
        update_booking, delete_booking, User, Booking,
        create_notification, get_unread_notifications, get_recent_notifications,
        mark_notification_as_read, mark_all_notifications_as_read,
        get_unread_notification_count, get_booking_by_id, check_student_double_booking,
        change_user_password, get_or_create_oauth_user
    )
    from config import *
    from dynamic_config import (
        get_period_times, get_period as _get_period_dict,
        get_fixed_offers, get_free_courses, get_school_classes_list,
        get_max_students, get_booking_advance_minutes,
        seed_initial_data,
    )
    from email_service import send_booking_notification
    from demo_mode import is_demo_mode, get_demo_bookings_for_week

    # IServ OAuth-Integration initialisieren
    from oauth_config import init_oauth, determine_user_role
    oauth_instance, iserv_client = init_oauth(app)

    # System-Konfiguration (Setup-Wizard)
    from system_config import is_setup_complete, get_branding, get_config

    # Datenbanktabellen erstellen (inkl. SystemConfig)
    with app.app_context():
        db.create_all()
        # Für bestehende Installationen mit vorhandenen Benutzern:
        # Setup als abgeschlossen markieren, damit keine Weiterleitung erfolgt
        try:
            from system_config import get_config, set_config
            from models import User, SystemConfig
            if get_config('setup_complete') is None:
                user_count = User.query.count()
                if user_count > 0:
                    set_config('setup_complete', 'true', category='system')
                    print("[SETUP] Bestehende Installation erkannt – Setup als abgeschlossen markiert.")
        except Exception as e:
            print(f"[SETUP] Hinweis: Setup-Check fehlgeschlagen: {e}")

        # Dynamische Konfiguration: Stunden/Kurse/Klassen aus Defaults einseeden
        try:
            seed_initial_data()
        except Exception as e:
            print(f"[DynConfig] Seeding beim Start fehlgeschlagen: {e}")

# Setup-Wizard Blueprint registrieren
from setup import setup_bp
app.register_blueprint(setup_bp)

# Admin-Blueprint für dynamische Konfiguration (Stunden/Kurse/Klassen)
from admin_dynamic import admin_dyn_bp
app.register_blueprint(admin_dyn_bp)

# ── before_request: Setup-Check ──────────────────────────────────────────────
@app.before_request
def check_setup():
    """Leitet zum Setup-Wizard weiter, wenn das System noch nicht eingerichtet ist."""
    # Statische Dateien und Setup-Routen nie blockieren
    if request.endpoint and (
        request.endpoint.startswith('setup.') or
        request.endpoint == 'static'
    ):
        return None
    # Wenn Setup noch nicht abgeschlossen → Wizard aufrufen
    try:
        if not is_setup_complete():
            return redirect(url_for('setup.index'))
    except Exception:
        # DB noch nicht bereit – Setup-Seite zeigen
        return redirect(url_for('setup.index'))
    return None

# ── Branding-Kontext für alle Templates ─────────────────────────────────────

def _hex_to_rgb(hex_color):
    """Konvertiert einen Hex-Farbwert in 'R, G, B' (kommagetrennt) und 'R G B' (leerzeichengetrennt)."""
    try:
        h = hex_color.lstrip('#')
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}", f"{r} {g} {b}"
    except Exception:
        return '233, 30, 99', '233 30 99'


def _resolve_logo_url(filename, default='logo.png'):
    """Gibt den URL-Pfad zur Logo-Datei zurück (uploads/ oder static root)."""
    if not filename:
        filename = default
    uploads_path = os.path.join('static', 'uploads', filename)
    if os.path.exists(uploads_path):
        return f'/static/uploads/{filename}'
    static_path = os.path.join('static', filename)
    if os.path.exists(static_path):
        return f'/static/{filename}'
    return f'/static/{default}'


@app.context_processor
def inject_demo_mode():
    """Macht den Demo-Modus-Status in allen Templates verfügbar."""
    try:
        demo = is_demo_mode()
    except Exception:
        demo = False
    return dict(demo_mode=demo)


@app.context_processor
def inject_branding():
    """Macht Branding-Variablen in allen Templates verfügbar."""
    try:
        branding = get_branding()
    except Exception:
        branding = {
            'school_name': 'SportOase',
            'school_subtitle': 'Buchungssystem',
            'primary_color': '#E91E63',
            'secondary_color': '#C2185B',
            'logo_filename': 'logo.png',
            'favicon_filename': 'logo.png',
            'background_color': '#fce4ec',
        }

    primary = branding.get('primary_color', '#E91E63')
    primary_rgb_comma, primary_rgb_space = _hex_to_rgb(primary)
    extra = {
        'logo_url': _resolve_logo_url(branding.get('logo_filename', 'logo.png')),
        'favicon_url': _resolve_logo_url(branding.get('favicon_filename', 'logo.png')),
        'primary_rgb': primary_rgb_comma,
        'primary_rgb_space': primary_rgb_space,
        'cms_privacy_text': get_config('cms_privacy_text', ''),
        'cms_imprint_text': get_config('cms_imprint_text', ''),
        'dashboard_notice': get_config('dashboard_notice', ''),
        'booking_notice':   get_config('booking_notice', ''),
    }
    return dict(branding=branding, **branding, **extra)

# Hilfsfunktion: Zeitzone Europe/Berlin
def get_berlin_tz():
    """Gibt die Zeitzone Europe/Berlin zurück"""
    return pytz.timezone('Europe/Berlin')

# Hilfsfunktion: Prüft, ob Benutzer eingeloggt ist
def login_required(f):
    """Decorator-Funktion: Schützt Routen, sodass nur eingeloggte Benutzer darauf zugreifen können"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte melden Sie sich an.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Hilfsfunktion: Prüft, ob Benutzer Admin ist
def admin_required(f):
    """Decorator-Funktion: Schützt Routen, sodass nur Admins darauf zugreifen können"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte melden Sie sich an.', 'error')
            return redirect(url_for('login'))
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'admin':
            flash('Zugriff verweigert. Nur Admins haben Zugriff.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Hilfsfunktion: Gibt Informationen über eine Stunde zurück
def get_period_info(weekday, period):
    """
    Gibt Informationen über eine Stunde zurück (fest/frei, Bezeichnung)
    weekday: z.B. "Mon", "Tue", ...
    period: 1-6
    """
    from models import get_custom_slot_name
    fixed_offers = get_fixed_offers()
    if weekday in fixed_offers and period in fixed_offers[weekday]:
        custom_label = get_custom_slot_name(weekday, period)
        label = custom_label if custom_label else fixed_offers[weekday][period]
        return {
            'type': 'fest',
            'label': label
        }
    else:
        return {
            'type': 'frei',
            'label': 'Freie Wahl'
        }

# Hilfsfunktion: Prüft, ob ein Datum in der Vergangenheit liegt
def is_past_date(check_date, period=None):
    """
    Prüft, ob ein Datum (und optional eine Stunde) in der Vergangenheit liegt
    """
    berlin_tz = get_berlin_tz()
    now = datetime.now(berlin_tz)
    
    if period is not None:
        # Prüfe mit spezifischer Stunde
        period_start_time = _get_period_dict(period)['start']
        hour, minute = map(int, period_start_time.split(':'))
        period_datetime = berlin_tz.localize(
            datetime.combine(check_date, datetime.min.time()).replace(hour=hour, minute=minute)
        )
        return period_datetime < now
    else:
        # Prüfe nur Datum
        today = now.date()
        return check_date < today

# Hilfsfunktion: Prüft, ob eine Buchung zeitlich möglich ist
def check_booking_time(booking_date, period):
    """
    Prüft, ob die Buchung mindestens 60 Minuten in der Zukunft liegt
    Gibt (True, None) zurück wenn OK, sonst (False, Fehlermeldung)
    """
    berlin_tz = get_berlin_tz()
    now = datetime.now(berlin_tz)
    
    # Erstelle Datetime-Objekt für den Stundenbeginn
    period_start_time = _get_period_dict(period)['start']
    hour, minute = map(int, period_start_time.split(':'))
    
    # Kombiniere Datum und Zeit
    period_datetime = berlin_tz.localize(
        datetime.combine(booking_date, datetime.min.time()).replace(hour=hour, minute=minute)
    )
    
    # Berechne Zeitdifferenz
    time_diff = period_datetime - now
    advance_mins = get_booking_advance_minutes()
    
    if time_diff.total_seconds() < advance_mins * 60:
        return False, f"Buchungen sind nur bis {advance_mins} Minuten vor Stundenbeginn möglich."
    
    return True, None

# Route: Startseite (leitet direkt zu IServ weiter)
@app.route('/')
def index():
    """Startseite - leitet zum Dashboard oder IServ-Login weiter"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    # Wenn IServ nicht konfiguriert, zeige Login-Seite
    if not iserv_client:
        return redirect(url_for('login'))
    return redirect(url_for('login_iserv'))

# Route: Direkter IServ-Embed Login (für iFrame-Integration)
@app.route('/iserv/embed')
def iserv_embed_login():
    """
    Direkter Login für IServ-Embed (iFrame) Integration.
    IServ sendet Benutzer-Informationen über URL-Parameter:
    - %user% → user Parameter
    - %email% → email Parameter
    - %domain% → domain Parameter (zur Verifizierung)
    
    Sicherheit:
    - Nur @kgs-pattensen.de E-Mails
    - Nur bereits registrierte Benutzer (neue müssen OAuth nutzen)
    - Zusätzliche Token-Validierung über ISERV_EMBED_SECRET
    """
    import hmac
    import hashlib
    import time
    
    user = request.args.get('user', '').strip()
    email = request.args.get('email', '').strip().lower()
    domain = request.args.get('domain', '').strip().lower()
    token = request.args.get('token', '').strip()
    timestamp = request.args.get('ts', '').strip()
    
    # Debug-Log
    print(f"🔐 IServ Embed Versuch: user={user}, email={email}, domain={domain}")
    
    # Prüfe ob alle Parameter vorhanden sind
    if not user or not email:
        flash('Ungültige IServ-Anmeldung.', 'error')
        return render_template('login.html')
    
    # Prüfe ob E-Mail zur Schule gehört (wichtigste Sicherheitsprüfung)
    if not email.endswith('@kgs-pattensen.de'):
        flash('Nur @kgs-pattensen.de E-Mail-Adressen sind erlaubt.', 'error')
        return render_template('login.html')
    
    # Optional: HMAC-Token Validierung (wenn ISERV_EMBED_SECRET gesetzt ist)
    embed_secret = os.environ.get('ISERV_EMBED_SECRET')
    if embed_secret:
        # Wenn Secret konfiguriert, muss Token gültig sein
        if not token or not timestamp:
            print(f"⚠️ IServ Embed: Token fehlt für {email}")
            flash('Ungültige Anmeldung (Token fehlt).', 'error')
            return render_template('login.html')
        
        # Prüfe Zeitstempel (max 5 Minuten alt)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:
                print(f"⚠️ IServ Embed: Token abgelaufen für {email}")
                flash('Anmeldung abgelaufen. Bitte erneut versuchen.', 'error')
                return render_template('login.html')
        except ValueError:
            flash('Ungültige Anmeldung.', 'error')
            return render_template('login.html')
        
        # Validiere HMAC
        expected = hmac.new(
            embed_secret.encode(),
            f"{email}:{timestamp}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(token, expected):
            print(f"⚠️ IServ Embed: Ungültiger Token für {email}")
            flash('Ungültige Anmeldung.', 'error')
            return render_template('login.html')
    
    # Hole bestehenden Benutzer aus der Datenbank
    existing_user = get_user_by_email(email)
    
    if existing_user:
        # Benutzer existiert bereits - direkt einloggen
        session['user_id'] = existing_user['id']
        session['user_username'] = existing_user['username']
        session['user_email'] = existing_user['email']
        session['user_role'] = existing_user['role']
        
        print(f"🔐 IServ Embed Login: {email} (bestehender Benutzer)")
        return redirect(url_for('dashboard'))
    else:
        # Neuer Benutzer - muss sich erst über OAuth registrieren
        flash('Bitte melden Sie sich einmalig über "Mit IServ anmelden" an.', 'info')
        return render_template('login.html')

# Route: Login-Seite (nur IServ-Button)
@app.route('/login')
def login():
    """Login-Seite - zeigt nur IServ-Login-Button, mit CMS-Texten"""
    login_title    = get_config('login_title', '')
    login_subtitle = get_config('login_subtitle', '')
    login_notice   = get_config('login_notice', '')
    return render_template('login.html',
                           login_title=login_title,
                           login_subtitle=login_subtitle,
                           login_notice=login_notice)

# Route: Lokaler Admin-Login (für Tests ohne IServ)
@app.route('/login/local', methods=['POST'])
def login_local():
    """Lokaler Admin-Login mit Benutzername und Passwort (nur für Admins)"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    if not username or not password:
        flash('Bitte Benutzername und Passwort eingeben.', 'error')
        return redirect(url_for('login'))

    user = get_user_by_username(username)
    if not user:
        flash('Ungültige Anmeldedaten.', 'error')
        return redirect(url_for('login'))

    if user['role'] != 'admin':
        flash('Lokaler Login ist nur für Administratoren verfügbar.', 'error')
        return redirect(url_for('login'))

    user_obj = User.query.filter_by(username=username).first()
    if not user_obj or not user_obj.password_hash or not user_obj.check_password(password):
        flash('Ungültige Anmeldedaten.', 'error')
        return redirect(url_for('login'))

    session.clear()
    session['user_id'] = user['id']
    session['user_username'] = user['username']
    session['user_email'] = user['email']
    session['user_role'] = user['role']

    flash(f'Willkommen, {username}! (Lokaler Admin-Login)', 'success')
    return redirect(url_for('dashboard'))


# Route: IServ SSO Login initiieren
@app.route('/login/iserv')
def login_iserv():
    """Startet den IServ OAuth2-Login-Flow"""
    if not iserv_client:
        flash('IServ-Login ist nicht konfiguriert. Bitte ISERV_CLIENT_ID und ISERV_CLIENT_SECRET in den Umgebungsvariablen setzen.', 'error')
        return redirect(url_for('login'))
    
    try:
        redirect_uri = url_for('oauth_callback', _external=True)
        print(f"🔐 IServ OAuth: Starte Login, Redirect URI: {redirect_uri}")
        return iserv_client.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"❌ IServ OAuth Fehler: {e}")
        flash(f'Fehler beim Starten des IServ-Logins: {str(e)}', 'error')
        return redirect(url_for('login'))

# Route: OAuth Callback von IServ
@app.route('/oauth/callback')
def oauth_callback():
    """Callback-Route für IServ OAuth2"""
    if not iserv_client:
        flash('IServ-Login ist nicht konfiguriert.', 'error')
        return redirect(url_for('login'))
    
    try:
        token = iserv_client.authorize_access_token()
        
        # === AUSFÜHRLICHES DEBUG-LOGGING ===
        print("=" * 80)
        print("🔐 ISERV OAUTH CALLBACK - VOLLSTÄNDIGE DEBUG-AUSGABE")
        print("=" * 80)
        
        # Token-Struktur analysieren
        print("\n📦 TOKEN KEYS:")
        token_keys = list(token.keys()) if isinstance(token, dict) else []
        for key in token_keys:
            print(f"   - {key}")
        
        # Prüfe ob roles/groups direkt im Token sind
        if 'roles' in token:
            print(f"\n📋 ROLES IM TOKEN: {token['roles']}")
        if 'groups' in token:
            print(f"\n👥 GROUPS IM TOKEN: {token['groups']}")
        
        # Userinfo aus Token oder separat abrufen
        userinfo = token.get('userinfo')
        print(f"\n📋 USERINFO AUS TOKEN: {'Ja' if userinfo else 'Nein'}")
        
        if not userinfo:
            print("   → Rufe userinfo separat ab...")
            userinfo = iserv_client.userinfo(token=token)
        
        # Vollständige Userinfo ausgeben
        print("\n📋 KOMPLETTE USERINFO:")
        print("-" * 60)
        if isinstance(userinfo, dict):
            for key, value in userinfo.items():
                value_str = str(value)
                if len(value_str) > 500:
                    value_str = value_str[:500] + "... [GEKÜRZT]"
                print(f"   {key}: {value_str}")
        else:
            print(f"   (Typ: {type(userinfo)}) {userinfo}")
        print("-" * 60)
        
        email = userinfo.get('email')
        sub = userinfo.get('sub')
        name = userinfo.get('name', email)
        
        print(f"\n👤 BENUTZER-DETAILS:")
        print(f"   E-Mail: {email}")
        print(f"   Sub-ID: {sub}")
        print(f"   Name: {name}")
        
        if not email or not sub:
            print("❌ FEHLER: E-Mail oder Sub-ID fehlt!")
            flash('Fehler beim Abrufen der Benutzerdaten von IServ.', 'error')
            return redirect(url_for('login'))
        
        # Prüfe auch ob Token selbst roles/groups enthält und füge sie zu userinfo hinzu
        if 'roles' in token and 'roles' not in userinfo:
            userinfo['roles'] = token['roles']
            print(f"\n   → Roles aus Token übernommen: {token['roles']}")
        if 'groups' in token and 'groups' not in userinfo:
            userinfo['groups'] = token['groups']
            print(f"\n   → Groups aus Token übernommen: {token['groups']}")
        
        # determine_user_role gibt jetzt (role, iserv_group) zurück
        role, iserv_group = determine_user_role(userinfo)
        
        print(f"\n🎯 ROLLENZUWEISUNG:")
        print(f"   App-Rolle: {role}")
        print(f"   IServ-Gruppe: {iserv_group}")
        print("=" * 80)
        
        # Prüfe ob Benutzer Zugang hat (nur Lehrer, Mitarbeitende, Administrator)
        if role is None:
            # Zeige detaillierte Fehlermeldung mit Hinweis auf IServ-Konfiguration
            error_msg = f'Zugang verweigert für {email}. '
            
            # Prüfe ob überhaupt roles/groups vorhanden sind
            has_roles = 'roles' in userinfo and userinfo['roles']
            has_groups = 'groups' in userinfo and userinfo['groups']
            
            if not has_roles and not has_groups:
                error_msg += 'IServ liefert keine Rollen/Gruppen. Bitte prüfen Sie die OAuth-Konfiguration in IServ (Scopes: roles, groups).'
                print(f"\n⚠️ WICHTIG: Keine Rollen/Gruppen von IServ erhalten!")
                print(f"   → Prüfen Sie in IServ unter: Admin → Single-Sign-On → App bearbeiten")
                print(f"   → Stellen Sie sicher, dass die Scopes 'roles' und 'groups' aktiviert sind!")
            else:
                error_msg += 'Keine berechtigte Rolle gefunden. Nur Schulleitung, Lehrer und Mitarbeitende haben Zugang.'
            
            flash(error_msg, 'error')
            print(f"❌ Zugang verweigert für: {email}")
            return redirect(url_for('login'))
        
        # Verwende E-Mail direkt als Username für OAuth-Benutzer
        user = get_or_create_oauth_user(
            email=email,
            username=email,
            oauth_provider='iserv',
            oauth_id=sub,
            role=role
        )
        
        if not user:
            flash('Fehler beim Erstellen des Benutzers.', 'error')
            return redirect(url_for('login'))
        
        # WICHTIG: Session komplett leeren, um OAuth-Token/userinfo zu entfernen
        session.clear()
        
        # Nur die wesentlichen Benutzerdaten speichern
        session['user_id'] = user['id']
        session['user_username'] = user['username']
        session['user_email'] = user['email']
        session['user_role'] = user['role']
        
        print(f"\n✅ LOGIN ERFOLGREICH: {email} → Rolle: {role}")
        flash(f'Willkommen, {name}!', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        import traceback
        print(f"\n❌ OAUTH FEHLER:")
        print(f"   Exception: {e}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        flash('Fehler beim IServ-Login. Bitte versuchen Sie es erneut.', 'error')
        return redirect(url_for('login'))

# Route: Logout
@app.route('/logout')
def logout():
    """Meldet den Benutzer ab"""
    session.clear()
    flash('Sie wurden abgemeldet.', 'info')
    return redirect(url_for('login'))

# Route: OAuth Debug - Zeigt Rollen/Gruppen-Daten von IServ
@app.route('/oauth/debug')
def oauth_debug():
    """
    Debug-Route: Zeigt die OAuth-Daten von IServ (nur für Admins sichtbar).
    Nützlich um zu sehen, welche Rollen/Gruppen IServ übergibt.
    """
    if 'user_id' not in session:
        flash('Bitte melden Sie sich an.', 'error')
        return redirect(url_for('login'))
    
    user = get_user_by_id(session['user_id'])
    if not user or user['role'] != 'admin':
        flash('Nur für Administratoren zugänglich.', 'error')
        return redirect(url_for('dashboard'))
    
    return '''
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <title>OAuth Debug - SportOase</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f5f5f5; }
            h1 { color: #333; }
            .card { background: white; padding: 20px; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .info { color: #666; }
            code { background: #e8e8e8; padding: 2px 6px; border-radius: 4px; }
            pre { background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 8px; overflow-x: auto; }
            .success { color: #22c55e; }
            .warning { color: #f59e0b; }
            a { color: #3b82f6; }
        </style>
    </head>
    <body>
        <h1>OAuth Debug Info</h1>
        
        <div class="card">
            <h2>Aktuelle Session</h2>
            <p><strong>User ID:</strong> ''' + str(session.get('user_id', 'N/A')) + '''</p>
            <p><strong>Username:</strong> ''' + str(session.get('user_username', 'N/A')) + '''</p>
            <p><strong>E-Mail:</strong> ''' + str(session.get('user_email', 'N/A')) + '''</p>
            <p><strong>Rolle:</strong> ''' + str(session.get('user_role', 'N/A')) + '''</p>
        </div>
        
        <div class="card">
            <h2>IServ OAuth Konfiguration</h2>
            <p><strong>Angeforderte Scopes:</strong> <code>openid profile email roles groups</code></p>
            <p class="info">Diese Scopes müssen in IServ Admin → Single-Sign-On für diese App aktiviert sein.</p>
        </div>
        
        <div class="card">
            <h2>So testen Sie die Rollen-Erkennung</h2>
            <ol>
                <li>Loggen Sie sich aus: <a href="/logout">Logout</a></li>
                <li>Loggen Sie sich erneut über IServ ein</li>
                <li>Prüfen Sie die Server-Logs (im Terminal/Workflow)</li>
                <li>Die Logs zeigen genau, welche Rollen/Gruppen IServ übergibt</li>
            </ol>
            <p class="warning">⚠️ Die OAuth-Daten werden aus Sicherheitsgründen nicht in der Session gespeichert.</p>
        </div>
        
        <div class="card">
            <h2>IServ Admin Einstellungen</h2>
            <p>In IServ unter <strong>Verwaltung → System → Single-Sign-On</strong>:</p>
            <ol>
                <li>Öffnen Sie die SportOase OAuth-App</li>
                <li>Unter "Beschränkungen → Auf Scopes beschränken" aktivieren Sie:
                    <ul>
                        <li>✓ OpenID</li>
                        <li>✓ E-Mail</li>
                        <li>✓ Profil</li>
                        <li>✓ <strong>Rollen</strong> (wichtig!)</li>
                        <li>✓ <strong>Gruppen</strong> (optional, als Fallback)</li>
                    </ul>
                </li>
                <li>Speichern Sie die Änderungen</li>
            </ol>
        </div>
        
        <p><a href="/dashboard">← Zurück zum Dashboard</a></p>
    </body>
    </html>
    '''

# Route: Passwort ändern
@app.route('/change_password', methods=['GET', 'POST'])
@admin_required
def change_password():
    """Ermöglicht Admins Passwörter zu ändern"""
    if request.method == 'POST':
        # CSRF-Token Validierung
        csrf_token = request.form.get('csrf_token', '')
        if not validate_csrf_token(csrf_token):
            flash('Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.', 'error')
            return redirect(url_for('change_password'))
        
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validierung
        if not old_password or not new_password or not confirm_password:
            flash('Bitte füllen Sie alle Felder aus.', 'error')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('Die neuen Passwörter stimmen nicht überein.', 'error')
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            flash('Das neue Passwort muss mindestens 6 Zeichen lang sein.', 'error')
            return redirect(url_for('change_password'))
        
        # Passwort ändern
        result = change_user_password(session['user_id'], old_password, new_password)
        
        if result['success']:
            flash(result['message'], 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(result['error'], 'error')
            return redirect(url_for('change_password'))
    
    return render_template('change_password.html')

# Route: Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    """Hauptseite - zeigt Wochenplan und Buchungsmöglichkeiten"""
    # Hole aktuelles Datum oder gewähltes Datum
    date_param = request.args.get('date')
    berlin_now = datetime.now(get_berlin_tz())
    
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except:
            selected_date = berlin_now.date()
    else:
        selected_date = berlin_now.date()
        # Ab Freitag 14:00 oder am Wochenende → automatisch zum nächsten Montag springen
        wd = selected_date.weekday()  # 0=Mo, 4=Fr, 5=Sa, 6=So
        if wd == 4 and berlin_now.hour >= 14:
            # Freitag ab 14 Uhr → nächster Montag (+3 Tage)
            selected_date += timedelta(days=3)
        elif wd == 5:
            # Samstag → nächster Montag (+2 Tage)
            selected_date += timedelta(days=2)
        elif wd == 6:
            # Sonntag → nächster Montag (+1 Tag)
            selected_date += timedelta(days=1)
            
    # WICHTIG: String-Repräsentation für Datenbank-Abfragen neu erstellen
    selected_date_str = selected_date.strftime('%Y-%m-%d')
    
    # Wochentag ermitteln (Mon, Tue, ...)
    weekday = selected_date.strftime('%a')
    weekday_name = selected_date.strftime('%A')  # Ausgeschriebener Name
    
    # Deutsche Wochentagsnamen
    weekday_names_de = {
        'Monday': 'Montag',
        'Tuesday': 'Dienstag',
        'Wednesday': 'Mittwoch',
        'Thursday': 'Donnerstag',
        'Friday': 'Freitag',
        'Saturday': 'Samstag',
        'Sunday': 'Sonntag'
    }
    weekday_name_de = weekday_names_de.get(weekday_name, weekday_name)
    
    # Erstelle Stundenplan für den Tag
    from models import is_slot_blocked, get_blocked_slot
    schedule = []
    for period in range(1, 7):
        period_info = get_period_info(weekday, period)
        student_count = count_students_for_period(selected_date_str, period)
        available = get_max_students() - student_count
        
        # Prüfe, ob Slot blockiert ist
        blocked_slot = get_blocked_slot(selected_date_str, period)
        is_blocked = blocked_slot is not None
        
        # Prüfe, ob Termin in der Vergangenheit liegt
        is_past = is_past_date(selected_date, period)
        
        # Prüfe, ob es ein Wochenende ist
        is_weekend = selected_date.weekday() in [5, 6]
        
        # Prüfe, ob Buchung zeitlich möglich ist
        can_book, time_message = check_booking_time(selected_date, period)
        
        # can_book muss False sein für vergangene Termine oder Wochenenden
        if is_past:
            can_book = False
            if not time_message:
                time_message = "Dieser Termin liegt in der Vergangenheit."
        elif is_weekend:
            can_book = False
            if not time_message:
                time_message = "Buchungen sind am Wochenende nicht möglich."
        
        schedule.append({
            'period': period,
            'time': f"{_get_period_dict(period)['start']} - {_get_period_dict(period)['end']}",
            'type': period_info['type'],
            'label': period_info['label'],
            'booked': student_count,
            'available': available,
            'can_book': can_book and available > 0 and not is_blocked and not is_past and not is_weekend,
            'time_message': time_message,
            'blocked': blocked_slot,
            'blocked_reason': blocked_slot.get('reason', 'Beratung') if blocked_slot else None,
            'blocked_icon': blocked_slot.get('icon', '🔧') if blocked_slot else None,
            'is_past': is_past,
            'is_weekend': is_weekend
        })
    
    # Erstelle Wochenübersicht (Montag-Freitag) mit Buchungsdaten
    from models import get_bookings_for_week, get_blocked_slots_for_week, is_slot_blocked
    
    # Berechne Montag und Freitag der aktuellen Woche
    days_since_monday = selected_date.weekday()
    monday = selected_date - timedelta(days=days_since_monday)
    friday = monday + timedelta(days=4)
    
    # Berechne Kalenderwoche
    calendar_week = monday.isocalendar()[1]
    calendar_year = monday.isocalendar()[0]
    
    # Berechne vorherige und nächste Woche für Navigation
    prev_week_monday = monday - timedelta(days=7)
    next_week_monday = monday + timedelta(days=7)
    
    # Hole alle Buchungen für diese Woche
    week_bookings = get_bookings_for_week(monday.strftime('%Y-%m-%d'), friday.strftime('%Y-%m-%d'))
    
    # Hole alle blockierten Slots für diese Woche
    blocked_slots = get_blocked_slots_for_week(monday.strftime('%Y-%m-%d'), friday.strftime('%Y-%m-%d'))
    
    # Organisiere blockierte Slots nach Datum und Stunde
    blocked_by_date_period = {}
    for blocked in blocked_slots:
        key = f"{blocked['date']}_{blocked['period']}"
        blocked_by_date_period[key] = blocked
    
    # Organisiere Buchungen nach Datum und Stunde
    bookings_by_date_period = {}
    exclusive_by_date_period = {}
    pending_exclusive_by_date_period = {}
    
    for booking in week_bookings:
        booking_dict = dict(booking)
        key = f"{booking_dict['date']}_{booking_dict['period']}"
        if key not in bookings_by_date_period:
            bookings_by_date_period[key] = []
        
        students = json.loads(booking_dict['students_json']) if booking_dict.get('students_json') else []
        booking_info = {
            'teacher_name': booking_dict.get('teacher_name', 'N/A'),
            'teacher_class': booking_dict.get('teacher_class', 'N/A'),
            'teacher_id': booking_dict.get('teacher_id'),
            'student_count': len(students),
            'students': students,
            'offer_label': booking_dict.get('offer_label', 'N/A'),
            'is_exclusive': booking_dict.get('is_exclusive', False),
            'is_approved': booking_dict.get('is_approved', True)
        }
        bookings_by_date_period[key].append(booking_info)
        
        # Speichere exklusive genehmigte Buchungen separat
        if booking_dict.get('is_exclusive') and booking_dict.get('is_approved'):
            exclusive_by_date_period[key] = booking_info
        
        # Speichere ausstehende exklusive Buchungen (noch nicht genehmigt)
        if booking_dict.get('is_exclusive') and not booking_dict.get('is_approved'):
            pending_exclusive_by_date_period[key] = booking_info
    
    week_overview = []
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    weekday_names = ['Mo', 'Di', 'Mi', 'Do', 'Fr']
    
    for i, wd in enumerate(weekdays):
        day_date = monday + timedelta(days=i)
        day_date_str = day_date.strftime('%Y-%m-%d')
        
        day_schedule = []
        for period in range(1, 7):
            info = get_period_info(wd, period)
            key = f"{day_date_str}_{period}"
            period_bookings = bookings_by_date_period.get(key, [])
            blocked_slot = blocked_by_date_period.get(key)
            exclusive_booking = exclusive_by_date_period.get(key)
            
            total_students = sum(b['student_count'] for b in period_bookings)
            pending_exclusive = pending_exclusive_by_date_period.get(key)
            
            # Bei exklusiver Buchung ist der Slot voll belegt
            if exclusive_booking:
                available = 0
            else:
                available = get_max_students() - total_students
            
            # Prüfe, ob Termin in der Vergangenheit liegt
            is_past = is_past_date(day_date, period)
            
            # Prüfe, ob es ein Wochenende ist
            is_weekend = day_date.weekday() in [5, 6]
            
            # Prüfe, ob Buchung für diesen Slot möglich ist
            can_book, _ = check_booking_time(day_date, period)
            can_book = can_book and available > 0 and not blocked_slot and not is_past and not is_weekend and not exclusive_booking
            
            day_schedule.append({
                'period': period,
                'type': info['type'],
                'label': info['label'],
                'bookings': period_bookings,
                'total_students': total_students,
                'available': available,
                'can_book': can_book,
                'blocked': blocked_slot,
                'blocked_reason': blocked_slot.get('reason', 'Beratung') if blocked_slot else None,
                'blocked_icon': blocked_slot.get('icon', '🔧') if blocked_slot else None,
                'is_past': is_past,
                'is_weekend': is_weekend,
                'is_exclusive': exclusive_booking is not None,
                'exclusive_booking': exclusive_booking,
                'pending_exclusive': pending_exclusive
            })
        # Prüfe ob heute
        today = datetime.now(get_berlin_tz()).date()
        is_today = day_date == today
        
        week_overview.append({
            'weekday': wd,
            'name': weekday_names[i],
            'date': day_date_str,
            'date_formatted': day_date.strftime('%d.%m.'),
            'schedule': day_schedule,
            'is_today': is_today
        })
    
    # Hole anstehende blockierte Slots für den Liveticker (ab heute)
    from models import BlockedSlot, User
    today_str = datetime.now(get_berlin_tz()).strftime('%Y-%m-%d')
    upcoming_query = db.session.query(BlockedSlot, User.username)\
        .outerjoin(User, BlockedSlot.blocked_by == User.id)\
        .filter(BlockedSlot.date >= today_str)\
        .order_by(BlockedSlot.date, BlockedSlot.period)\
        .limit(15).all()
        
    upcoming_blocked = []
    for blocked, username in upcoming_query:
        try:
            date_obj = datetime.strptime(blocked.date, '%Y-%m-%d')
            wd_de = {'Mon': 'Mo', 'Tue': 'Di', 'Wed': 'Mi', 'Thu': 'Do', 'Fri': 'Fr', 'Sat': 'Sa', 'Sun': 'So'}.get(blocked.weekday, blocked.weekday)
            date_formatted = f"{wd_de} {date_obj.strftime('%d.%m.')}"
        except:
            date_formatted = blocked.date
            
        upcoming_blocked.append({
            'id': blocked.id,
            'date': blocked.date,
            'date_formatted': date_formatted,
            'period': blocked.period,
            'reason': blocked.reason,
            'icon': blocked.icon or '🔧',
            'blocked_by_id': blocked.blocked_by,
            'blocked_by_name': username or 'System'
        })
    
    # Hole eigene anstehende Buchungen & ausstehende Exklusiv-Anfragen
    from models import Booking
    user_id = session.get('user_id')
    user_role = session.get('user_role')
    
    upcoming_bookings = []
    pending_approvals = []
    
    if user_id:
        # Eigene Buchungen ab heute
        my_bookings_query = Booking.query.filter(
            Booking.teacher_id == user_id,
            Booking.date >= today_str
        ).order_by(Booking.date, Booking.period).limit(5).all()
        
        for booking in my_bookings_query:
            try:
                date_obj = datetime.strptime(booking.date, '%Y-%m-%d')
                wd_de = {'Mon': 'Mo', 'Tue': 'Di', 'Wed': 'Mi', 'Thu': 'Do', 'Fri': 'Fr', 'Sat': 'Sa', 'Sun': 'So'}.get(booking.weekday, booking.weekday)
                date_formatted = f"{wd_de} {date_obj.strftime('%d.%m.')}"
            except:
                date_formatted = booking.date
            
            try:
                students = json.loads(booking.students_json)
                students_str = ", ".join([f"{s.get('name')} ({s.get('klasse')})" for s in students])
            except:
                students_str = ""
                
            upcoming_bookings.append({
                'id': booking.id,
                'date': booking.date,
                'date_formatted': date_formatted,
                'period': booking.period,
                'offer_label': booking.offer_label,
                'is_exclusive': booking.is_exclusive,
                'is_approved': booking.is_approved,
                'students_str': students_str
            })
            
        # Admin-Ausstehende exklusive Anfragen ab heute
        if user_role == 'admin':
            pending_query = Booking.query.filter(
                Booking.is_exclusive == True,
                Booking.is_approved == False,
                Booking.date >= today_str
            ).order_by(Booking.date, Booking.period).all()
            
            for p_booking in pending_query:
                try:
                    date_obj = datetime.strptime(p_booking.date, '%Y-%m-%d')
                    wd_de = {'Mon': 'Mo', 'Tue': 'Di', 'Wed': 'Mi', 'Thu': 'Do', 'Fri': 'Fr', 'Sat': 'Sa', 'Sun': 'So'}.get(p_booking.weekday, p_booking.weekday)
                    date_formatted = f"{wd_de} {date_obj.strftime('%d.%m.')}"
                except:
                    date_formatted = p_booking.date
                
                try:
                    students = json.loads(p_booking.students_json)
                    students_str = ", ".join([f"{s.get('name')} ({s.get('klasse')})" for s in students])
                except:
                    students_str = ""
                    
                pending_approvals.append({
                    'id': p_booking.id,
                    'date': p_booking.date,
                    'date_formatted': date_formatted,
                    'period': p_booking.period,
                    'teacher_name': p_booking.teacher_name,
                    'students_str': students_str,
                    'offer_label': p_booking.offer_label
                })
    
    # Generiere Wochenliste für den Kalenderwochen-Schnellwähler
    week_selector = []
    real_today = datetime.now(get_berlin_tz()).date()
    real_monday = real_today - timedelta(days=real_today.weekday())
    
    for w in range(8):
        loop_monday = real_monday + timedelta(weeks=w)
        loop_friday = loop_monday + timedelta(days=4)
        loop_kw = loop_monday.isocalendar()[1]
        
        label = f"KW {loop_kw:02d} ({loop_monday.strftime('%d.%m.')} – {loop_friday.strftime('%d.%m.')})"
        date_str = loop_monday.strftime('%Y-%m-%d')
        is_selected = (loop_monday.strftime('%Y-%m-%d') == monday.strftime('%Y-%m-%d'))
        
        week_selector.append({
            'label': label,
            'date': date_str,
            'is_selected': is_selected
        })
    
    return render_template('dashboard.html',
                         week_selector=week_selector,
                         selected_date=selected_date,
                         weekday=weekday_name_de,
                         schedule=schedule,
                         week_overview=week_overview,
                         upcoming_blocked=upcoming_blocked,
                         upcoming_bookings=upcoming_bookings,
                         pending_approvals=pending_approvals,
                         user_role=user_role,
                         current_user_id=user_id,
                         calendar_week=calendar_week,
                         calendar_year=calendar_year,
                         prev_week_date=prev_week_monday.strftime('%Y-%m-%d'),
                         next_week_date=next_week_monday.strftime('%Y-%m-%d'),
                         monday_date=monday.strftime('%d.%m.%Y'),
                         friday_date=friday.strftime('%d.%m.%Y'))

# Route: Kalenderansicht (Monats-/Jahresübersicht)
@app.route('/calendar')
@app.route('/calendar/<int:year>/<int:month>')
@login_required
def calendar_view(year=None, month=None):
    """Monats-/Jahreskalenderansicht mit Buchungsübersicht"""
    import calendar
    from models import get_bookings_for_week, get_blocked_slots_for_week
    
    # Aktuelles Datum
    today = datetime.now(get_berlin_tz()).date()
    
    # Standard: aktueller Monat
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    
    # Validierung
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1
    
    # Deutsche Monatsnamen
    month_names_de = {
        1: 'Januar', 2: 'Februar', 3: 'März', 4: 'April',
        5: 'Mai', 6: 'Juni', 7: 'Juli', 8: 'August',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Dezember'
    }
    
    # Kalender erstellen
    cal = calendar.Calendar(firstweekday=0)  # Montag als erster Tag
    month_days = cal.monthdayscalendar(year, month)
    
    # Ersten und letzten Tag des Monats ermitteln
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Buchungen und blockierte Slots für den gesamten Monat holen
    from models import Booking, BlockedSlot
    
    month_bookings = Booking.query.filter(
        Booking.date >= first_day.strftime('%Y-%m-%d'),
        Booking.date <= last_day.strftime('%Y-%m-%d')
    ).all()
    
    month_blocked = BlockedSlot.query.filter(
        BlockedSlot.date >= first_day.strftime('%Y-%m-%d'),
        BlockedSlot.date <= last_day.strftime('%Y-%m-%d')
    ).all()
    
    # Zähle Buchungen pro Tag
    bookings_per_day = {}
    for booking in month_bookings:
        day_key = booking.date
        if day_key not in bookings_per_day:
            bookings_per_day[day_key] = 0
        students = json.loads(booking.students_json) if booking.students_json else []
        bookings_per_day[day_key] += len(students)
    
    # Zähle blockierte Slots pro Tag
    blocked_per_day = {}
    blocked_reasons = {}
    for blocked in month_blocked:
        day_key = blocked.date
        if day_key not in blocked_per_day:
            blocked_per_day[day_key] = 0
            blocked_reasons[day_key] = blocked.reason or 'Blockiert'
        blocked_per_day[day_key] += 1
    
    # Kalenderwochen erstellen mit Infos
    weeks = []
    for week in month_days:
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                day_date = date(year, month, day_num)
                day_str = day_date.strftime('%Y-%m-%d')
                is_weekend = day_date.weekday() in [5, 6]
                is_today = day_date == today
                is_past = day_date < today
                
                booking_count = bookings_per_day.get(day_str, 0)
                blocked_count = blocked_per_day.get(day_str, 0)
                blocked_reason = blocked_reasons.get(day_str, '')
                
                # Status ermitteln
                if is_weekend:
                    status = 'weekend'
                elif blocked_count >= 6:  # Alle 6 Stunden blockiert
                    status = 'blocked'
                elif blocked_count > 0:
                    status = 'partial_blocked'
                elif booking_count >= 30:  # 6 Stunden * 5 Plätze = 30
                    status = 'full'
                elif booking_count > 0:
                    status = 'has_bookings'
                else:
                    status = 'free'
                
                week_data.append({
                    'day': day_num,
                    'date': day_str,
                    'is_weekend': is_weekend,
                    'is_today': is_today,
                    'is_past': is_past,
                    'booking_count': booking_count,
                    'blocked_count': blocked_count,
                    'blocked_reason': blocked_reason,
                    'status': status
                })
        weeks.append(week_data)
    
    # Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    return render_template('calendar.html',
                         year=year,
                         month=month,
                         month_name=month_names_de[month],
                         weeks=weeks,
                         today=today,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month,
                         user_role=session.get('user_role'))

# Route: Buchungsseite
@app.route('/book/<date_str>/<int:period>', methods=['GET', 'POST'])
@login_required
def book(date_str, period):
    """Seite zum Erstellen einer neuen Buchung"""

    # Im Demo-Modus sind keine echten Buchungen möglich
    if is_demo_mode():
        flash('Im Demo-Modus können keine Buchungen erstellt werden.', 'error')
        return redirect(url_for('dashboard'))

    # Hole den Benutzernamen aus der Session für das Formular
    user_display_name = session.get('user_username', '')
    # Falls E-Mail als Username verwendet wird, extrahiere den Namen
    if '@' in user_display_name:
        user_display_name = user_display_name.split('@')[0].replace('.', ' ').title()
    
    # Validiere Datum und Stunde
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        flash('Ungültiges Datum.', 'error')
        return redirect(url_for('dashboard'))
    
    if period < 1 or period > 6:
        flash('Ungültige Stunde.', 'error')
        return redirect(url_for('dashboard'))
    
    # Prüfe, ob Termin in der Vergangenheit liegt
    if is_past_date(booking_date, period):
        flash('Dieser Termin liegt in der Vergangenheit und kann nicht gebucht werden.', 'error')
        return redirect(url_for('dashboard'))
    
    # Prüfe, ob es ein Wochenende ist (Samstag=5, Sonntag=6)
    if booking_date.weekday() in [5, 6]:
        flash('Buchungen sind am Wochenende nicht möglich.', 'error')
        return redirect(url_for('dashboard'))
    
    # Ermittle Wochentag und Stundeninfo
    weekday = booking_date.strftime('%a')
    period_info = get_period_info(weekday, period)
    
    # Prüfe verfügbare Plätze
    current_students = count_students_for_period(date_str, period)
    available_spots = get_max_students() - current_students
    
    if available_spots <= 0:
        flash('Diese Stunde ist bereits voll belegt.', 'error')
        return redirect(url_for('dashboard', date=date_str))
    
    # Prüfe, ob Slot für Beratung blockiert ist (nur Admins können blockierte Slots sehen)
    from models import is_slot_blocked, get_blocked_slot
    if is_slot_blocked(date_str, period):
        blocked_info = get_blocked_slot(date_str, period)
        reason = blocked_info.get('reason', 'Beratung') if blocked_info else 'Beratung'
        flash(f'Dieser Slot ist für {reason} blockiert und kann nicht gebucht werden.', 'error')
        return redirect(url_for('dashboard', date=date_str))
    
    # Prüfe, ob bereits eine genehmigte exklusive Buchung existiert
    from models import Booking
    exclusive_booking = Booking.query.filter_by(
        date=date_str,
        period=period,
        is_exclusive=True,
        is_approved=True
    ).first()
    if exclusive_booking:
        flash('Dieser Slot ist für ein Einzelangebot reserviert und kann nicht gebucht werden.', 'error')
        return redirect(url_for('dashboard', date=date_str))
    
    # Prüfe Zeitfenster
    can_book, time_message = check_booking_time(booking_date, period)
    if not can_book:
        flash(time_message or 'Buchung nicht möglich.', 'error')
        return redirect(url_for('dashboard', date=date_str))
    
    if request.method == 'POST':
        # Hole Lehrkraft-Informationen
        teacher_name = request.form.get('teacher_name', '').strip()
        teacher_class = request.form.get('teacher_class', '').strip()
        
        if not teacher_name or not teacher_class:
            flash('Bitte geben Sie Ihren Namen und Ihre Klasse ein.', 'error')
            return render_template('book.html', 
                                 date_str=date_str,
                                 period=period,
                                 period_info=period_info,
                                 period_time=_get_period_dict(period),
                                 available_spots=available_spots,
                                 free_modules=get_free_courses(),
                                 user_name=user_display_name,
                                 school_classes=get_school_classes_list())
        
        # Hole Anzahl der Schüler
        num_students = int(request.form.get('num_students', 1))
        
        if num_students < 1 or num_students > 5:
            flash('Bitte wählen Sie zwischen 1 und 5 Schülern.', 'error')
            return render_template('book.html', 
                                 date_str=date_str,
                                 period=period,
                                 period_info=period_info,
                                 period_time=_get_period_dict(period),
                                 available_spots=available_spots,
                                 free_modules=get_free_courses(),
                                 user_name=user_display_name,
                                 school_classes=get_school_classes_list())
        
        # Prüfe erneut verfügbare Plätze
        if num_students > available_spots:
            flash(f'Nicht genug Plätze verfügbar. Nur noch {available_spots} Plätze frei.', 'error')
            return redirect(url_for('dashboard', date=date_str))
        
        # Sammle Schülerdaten und prüfe Doppelbuchungen
        students = []
        for i in range(num_students):
            name = request.form.get(f'student_name_{i}', '').strip()
            klasse = request.form.get(f'student_class_{i}', '').strip()
            
            if not name or not klasse:
                flash('Bitte füllen Sie alle Schülerfelder aus.', 'error')
                return render_template('book.html', 
                                     date_str=date_str,
                                     period=period,
                                     period_info=period_info,
                                     period_time=_get_period_dict(period),
                                     available_spots=available_spots,
                                     free_modules=get_free_courses(),
                                     user_name=user_display_name,
                                     school_classes=get_school_classes_list())
            
            # Prüfe auf Doppelbuchung
            double_booking = check_student_double_booking(name, klasse, date_str, period)
            if double_booking['is_booked']:
                flash(f'⚠️ Doppelbuchung verhindert: {double_booking["booking_info"]}', 'error')
                return render_template('book.html', 
                                     date_str=date_str,
                                     period=period,
                                     period_info=period_info,
                                     period_time=_get_period_dict(period),
                                     available_spots=available_spots,
                                     free_modules=get_free_courses(),
                                     user_name=user_display_name,
                                     school_classes=get_school_classes_list())
            
            students.append({'name': name, 'klasse': klasse})
        
        # Hole Modul-Wahl (nur bei freien Stunden)
        if period_info['type'] == 'frei':
            selected_module = request.form.get('module', '')
            if selected_module not in get_free_courses():
                flash('Bitte wählen Sie ein Modul.', 'error')
                return render_template('book.html', 
                                     date_str=date_str,
                                     period=period,
                                     period_info=period_info,
                                     period_time=_get_period_dict(period),
                                     available_spots=available_spots,
                                     free_modules=get_free_courses(),
                                     user_name=user_display_name,
                                     school_classes=get_school_classes_list())
            offer_label = selected_module
        else:
            offer_label = period_info['label']
        
        # Hole optionale Notizen
        notes = request.form.get('notes', '').strip()
        
        # Prüfe ob exklusive Buchung (nur 1 Schüler)
        is_exclusive = request.form.get('is_exclusive') == '1' and len(students) == 1
        
        # Erstelle Buchung in Datenbank
        booking_id = create_booking(
            date=date_str,
            weekday=weekday,
            period=period,
            teacher_id=session['user_id'],
            students=students,
            offer_type=period_info['type'],
            offer_label=offer_label,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            notes=notes if notes else None,
            is_exclusive=is_exclusive
        )
        
        if booking_id:
            # Sende E-Mail-Benachrichtigung
            booking_data = {
                'date': date_str,
                'weekday': weekday,
                'period': period,
                'students': students,
                'offer_type': period_info['type'],
                'offer_label': offer_label,
                'teacher_name': teacher_name,
                'teacher_class': teacher_class,
                'students_json': json.dumps(students, ensure_ascii=False),
                'is_exclusive': is_exclusive
            }
            
            # Erstelle Notification in der Datenbank
            if is_exclusive:
                notification_message = f"🔒 EXKLUSIVE Buchung (Freigabe nötig): {teacher_name} möchte 1 Schüler exklusiv für {offer_label} am {date_str} (Stunde {period}) anmelden."
                notification_type = 'exclusive_booking_pending'
            else:
                notification_message = f"Neue Buchung: {teacher_name} hat {len(students)} Schüler für {offer_label} am {date_str} (Stunde {period}) angemeldet."
                notification_type = 'new_booking'
            
            notification_id = create_notification(
                booking_id=booking_id,
                message=notification_message,
                notification_type=notification_type,
                recipient_role='admin',
                metadata={
                    'teacher_name': teacher_name,
                    'teacher_class': teacher_class,
                    'date': date_str,
                    'period': period,
                    'offer_label': offer_label,
                    'students_count': len(students),
                    'is_exclusive': is_exclusive
                }
            )
            
            # Sende E-Mail-Benachrichtigung an Admin (SMTP)
            try:
                send_booking_notification(booking_data)
            except Exception as e:
                print(f"E-Mail-Benachrichtigung fehlgeschlagen: {e}")
            
            # Sende E-Mail-Bestätigung an Lehrer (nur wenn Checkbox aktiviert)
            send_email_confirmation = request.form.get('send_email_confirmation') == '1'
            
            # Hole E-Mail direkt aus der Datenbank (zuverlässiger als Session)
            user_id = session.get('user_id')
            user_email = ''
            if user_id:
                user_data = get_user_by_id(user_id)
                if user_data:
                    user_email = user_data.get('email', '')
            
            print(f"[BUCHUNG] E-Mail-Checkbox aktiviert: {send_email_confirmation}")
            print(f"[BUCHUNG] User ID: {user_id}")
            print(f"[BUCHUNG] User E-Mail (aus DB): {user_email}")
            
            if send_email_confirmation and user_email:
                print(f"[BUCHUNG] Versuche E-Mail-Bestätigung an {user_email} zu senden...")
                try:
                    if is_exclusive:
                        # Bei Einzelbuchung: "Buchung steht aus" statt "erfolgreich gebucht"
                        from email_service import send_exclusive_pending_email
                        result = send_exclusive_pending_email(user_email, booking_data)
                        print(f"[BUCHUNG] Einzelbuchung-Pending-E-Mail Ergebnis: {result}")
                    else:
                        # Normale Buchung: Standard-Bestätigung
                        from email_service import send_user_booking_confirmation
                        result = send_user_booking_confirmation(user_email, booking_data)
                        print(f"[BUCHUNG] E-Mail-Versand Ergebnis: {result}")
                except Exception as e:
                    print(f"[BUCHUNG] Benutzer-E-Mail-Bestätigung fehlgeschlagen: {e}")
            else:
                print(f"[BUCHUNG] Keine E-Mail gesendet (Checkbox: {send_email_confirmation}, Email vorhanden: {bool(user_email)})")
            
            # Broadcast an SSE-Clients
            if notification_id:
                unread_count = get_unread_notification_count(recipient_role='admin')
                broadcast_notification({
                    'type': 'new_booking',
                    'notification_id': notification_id,
                    'message': notification_message,
                    'booking_data': {
                        'date': date_str,
                        'period': period,
                        'teacher_name': teacher_name,
                        'offer_label': offer_label,
                        'students_count': len(students)
                    },
                    'unread_count': unread_count
                })
            
            if is_exclusive:
                flash(f'Exklusive Buchung eingereicht! Die Buchung wartet auf Freigabe durch den Admin. Sie werden per E-Mail benachrichtigt.', 'info')
            else:
                flash(f'Buchung erfolgreich! {len(students)} Schüler für {offer_label} angemeldet.', 'success')
            return redirect(url_for('dashboard', date=date_str))
        else:
            flash('Fehler beim Erstellen der Buchung.', 'error')
    
    # Hole E-Mail aus der Datenbank für die Anzeige
    display_user_email = ''
    user_id = session.get('user_id')
    if user_id:
        user_data = get_user_by_id(user_id)
        if user_data:
            display_user_email = user_data.get('email', '')
    
    return render_template('book.html',
                         date_str=date_str,
                         period=period,
                         period_info=period_info,
                         period_time=_get_period_dict(period),
                         available_spots=available_spots,
                         free_modules=get_free_courses(),
                         user_name=user_display_name,
                         user_email=display_user_email,
                         school_classes=get_school_classes_list())

# Hilfsfunktion: Prüft ob eine Buchung noch bearbeitet/gelöscht werden kann
def can_modify_booking(booking_date_str, period):
    """
    Prüft ob eine Buchung noch bearbeitet/gelöscht werden kann.
    Änderungen sind bis 1 Stunde vor dem Termin möglich.
    
    Returns:
        Tuple (can_modify: bool, reason: str or None)
    """
    try:
        booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        now = datetime.now(get_berlin_tz())
        today = now.date()
        
        # Vergangenes Datum?
        if booking_date < today:
            return False, "Vergangener Termin"
        
        # Heute: Prüfe ob weniger als 1 Stunde bis zum Termin
        if booking_date == today:
            period_start_str = _get_period_dict(period)['start']
            period_start_time = datetime.strptime(period_start_str, '%H:%M').time()
            period_start = datetime.combine(today, period_start_time)
            period_start = get_berlin_tz().localize(period_start)
            
            # 1 Stunde vor Beginn
            cutoff_time = period_start - timedelta(hours=1)
            
            if now >= cutoff_time:
                return False, "Weniger als 1 Stunde vor Termin"
        
        return True, None
    except Exception as e:
        print(f"Fehler bei can_modify_booking: {e}")
        return False, "Fehler bei der Prüfung"

# Route: Meine Buchungen
@app.route('/meine-buchungen')
@login_required
def meine_buchungen():
    """Zeigt alle Buchungen des Benutzers (oder alle für Admin)"""
    from models import get_all_bookings, Booking
    
    user_id = session['user_id']
    is_admin = session.get('user_role') == 'admin'
    
    # Admin sieht alle Buchungen, normale Benutzer nur ihre eigenen
    if is_admin:
        all_bookings = get_all_bookings()
    else:
        bookings_query = Booking.query.filter_by(teacher_id=user_id).order_by(Booking.date.desc(), Booking.period).all()
        all_bookings = [b.to_dict() for b in bookings_query]
    
    # Deutsche Wochentagsnamen
    weekday_names_de = {
        'Mon': 'Montag', 'Tue': 'Dienstag', 'Wed': 'Mittwoch',
        'Thu': 'Donnerstag', 'Fri': 'Freitag', 'Sat': 'Samstag', 'Sun': 'Sonntag'
    }
    
    bookings_display = []
    for booking in all_bookings:
        booking_dict = dict(booking)
        students = json.loads(booking_dict['students_json']) if booking_dict.get('students_json') else []
        
        # Prüfe ob Buchung bearbeitet/gelöscht werden kann
        can_modify, modify_reason = can_modify_booking(booking_dict['date'], booking_dict['period'])
        
        # Admin kann immer bearbeiten
        if is_admin:
            can_modify = True
            modify_reason = None
        
        # Datum formatieren
        try:
            booking_date = datetime.strptime(booking_dict['date'], '%Y-%m-%d').date()
            date_formatted = booking_date.strftime('%d.%m.%Y')
            is_past = booking_date < datetime.now(get_berlin_tz()).date()
        except:
            date_formatted = booking_dict['date']
            is_past = False
        
        # Created_at formatieren
        created_at = booking_dict.get('created_at', '')
        if created_at:
            try:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    created_dt = created_at
                created_at_formatted = created_dt.strftime('%d.%m.%Y %H:%M')
            except:
                created_at_formatted = str(created_at)
        else:
            created_at_formatted = '-'
        
        bookings_display.append({
            'id': booking_dict['id'],
            'date': booking_dict['date'],
            'date_formatted': date_formatted,
            'weekday': booking_dict['weekday'],
            'weekday_name': weekday_names_de.get(booking_dict['weekday'], booking_dict['weekday']),
            'period': booking_dict['period'],
            'period_time': f"{_get_period_dict(booking_dict['period'])['start']} - {_get_period_dict(booking_dict['period'])['end']}",
            'teacher_name': booking_dict.get('teacher_name', 'N/A'),
            'teacher_class': booking_dict.get('teacher_class', 'N/A'),
            'offer_label': booking_dict['offer_label'],
            'offer_type': booking_dict['offer_type'],
            'students': students,
            'can_modify': can_modify,
            'modify_reason': modify_reason,
            'is_past': is_past,
            'created_at_formatted': created_at_formatted
        })
    
    return render_template('meine_buchungen.html',
                         bookings=bookings_display,
                         is_admin=is_admin)

# Route: Eigene Buchung bearbeiten
@app.route('/meine-buchungen/bearbeiten/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def edit_my_booking(booking_id):
    """Benutzer kann eigene Buchung bearbeiten (bis 1 Stunde vorher)"""
    from models import get_booking_by_id, update_booking, Booking
    
    user_id = session['user_id']
    is_admin = session.get('user_role') == 'admin'
    
    booking_row = get_booking_by_id(booking_id)
    if not booking_row:
        flash('Buchung nicht gefunden.', 'error')
        return redirect(url_for('meine_buchungen'))
    
    booking = dict(booking_row)
    
    # Prüfe Berechtigung: Eigene Buchung oder Admin
    if booking['teacher_id'] != user_id and not is_admin:
        flash('Sie können nur Ihre eigenen Buchungen bearbeiten.', 'error')
        return redirect(url_for('meine_buchungen'))
    
    # Prüfe ob Bearbeitung noch möglich ist (außer Admin)
    if not is_admin:
        can_modify, modify_reason = can_modify_booking(booking['date'], booking['period'])
        if not can_modify:
            flash(f'Diese Buchung kann nicht mehr bearbeitet werden: {modify_reason}', 'error')
            return redirect(url_for('meine_buchungen'))
    
    # Deutsche Wochentagsnamen
    weekday_names_de = {
        'Mon': 'Montag', 'Tue': 'Dienstag', 'Wed': 'Mittwoch',
        'Thu': 'Donnerstag', 'Fri': 'Freitag', 'Sat': 'Samstag', 'Sun': 'Sonntag'
    }
    
    students = json.loads(booking['students_json']) if booking.get('students_json') else []
    
    # Berechne verfügbare Plätze (ohne die aktuelle Buchung)
    current_students = count_students_for_period(booking['date'], booking['period'])
    available_spots = get_max_students() - (current_students - len(students))
    
    # Datum formatieren
    try:
        booking_date = datetime.strptime(booking['date'], '%Y-%m-%d').date()
        date_formatted = booking_date.strftime('%d.%m.%Y')
    except:
        date_formatted = booking['date']
    
    if request.method == 'POST':
        # CSRF-Token Validierung
        csrf_token = request.form.get('csrf_token', '')
        if not validate_csrf_token(csrf_token):
            flash('Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.', 'error')
            return redirect(url_for('edit_my_booking', booking_id=booking_id))
        
        try:
            num_students = int(request.form.get('num_students', 1))
        except (ValueError, TypeError):
            flash('Ungültige Schüleranzahl.', 'error')
            return redirect(url_for('edit_my_booking', booking_id=booking_id))
        
        if num_students < 1 or num_students > available_spots:
            flash(f'Bitte wählen Sie zwischen 1 und {available_spots} Schüler*innen.', 'error')
            return redirect(url_for('edit_my_booking', booking_id=booking_id))
        
        # Sammle Schülerdaten
        new_students = []
        for i in range(num_students):
            name = request.form.get(f'student_name_{i}', '').strip()
            klasse = request.form.get(f'student_class_{i}', '').strip()
            
            if not name or not klasse:
                flash('Bitte füllen Sie alle Schülerfelder aus.', 'error')
                return redirect(url_for('edit_my_booking', booking_id=booking_id))
            
            # Prüfe auf Doppelbuchung (außer bei der aktuellen Buchung)
            double_booking = check_student_double_booking(name, klasse, booking['date'], booking['period'], exclude_booking_id=booking_id)
            if double_booking['is_booked']:
                flash(f'⚠️ Doppelbuchung verhindert: {double_booking["booking_info"]}', 'error')
                return redirect(url_for('edit_my_booking', booking_id=booking_id))
            
            new_students.append({'name': name, 'klasse': klasse})
        
        # Hole Modul-Wahl (nur bei freien Stunden)
        if booking['offer_type'] == 'frei':
            selected_module = request.form.get('module', '')
            if selected_module not in get_free_courses():
                flash('Bitte wählen Sie ein Modul.', 'error')
                return redirect(url_for('edit_my_booking', booking_id=booking_id))
            offer_label = selected_module
        else:
            offer_label = booking['offer_label']
        
        # Aktualisiere Buchung (Notizen bleiben unverändert bei Lehrer-Bearbeitung)
        if update_booking(
            booking_id=booking_id,
            date=booking['date'],
            weekday=booking['weekday'],
            period=booking['period'],
            teacher_id=booking['teacher_id'],
            students=new_students,
            offer_type=booking['offer_type'],
            offer_label=offer_label,
            teacher_name=booking.get('teacher_name'),
            teacher_class=booking.get('teacher_class'),
            notes=booking.get('notes')
        ):
            flash('Buchung erfolgreich aktualisiert!', 'success')
            return redirect(url_for('meine_buchungen'))
        else:
            flash('Fehler beim Aktualisieren der Buchung.', 'error')
    
    # Booking-Objekt für Template vorbereiten
    booking_display = {
        'id': booking['id'],
        'date': booking['date'],
        'date_formatted': date_formatted,
        'weekday': booking['weekday'],
        'weekday_name': weekday_names_de.get(booking['weekday'], booking['weekday']),
        'period': booking['period'],
        'offer_label': booking['offer_label'],
        'offer_type': booking['offer_type'],
        'students': students
    }
    
    return render_template('edit_my_booking.html',
                         booking=booking_display,
                         period_times=get_period_times(),
                         free_modules=get_free_courses(),
                         school_classes=get_school_classes_list(),
                         max_students=available_spots,
                         available_spots=available_spots - len(students))

# Route: Eigene Buchung löschen
@app.route('/meine-buchungen/loeschen/<int:booking_id>', methods=['POST'])
@login_required
def delete_my_booking(booking_id):
    """Benutzer kann eigene Buchung löschen (bis 1 Stunde vorher)"""
    from models import get_booking_by_id, delete_booking
    
    # CSRF-Token Validierung
    csrf_token = request.form.get('csrf_token', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'
    
    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Ungültiges Sicherheits-Token.'}), 400
        flash('Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.', 'error')
        return redirect(url_for('meine_buchungen'))
    
    user_id = session['user_id']
    is_admin = session.get('user_role') == 'admin'
    
    booking_row = get_booking_by_id(booking_id)
    if not booking_row:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Buchung nicht gefunden.'}), 404
        flash('Buchung nicht gefunden.', 'error')
        return redirect(url_for('meine_buchungen'))
    
    booking = dict(booking_row)
    
    # Prüfe Berechtigung: Eigene Buchung oder Admin
    if booking['teacher_id'] != user_id and not is_admin:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sie können nur Ihre eigenen Buchungen löschen.'}), 403
        flash('Sie können nur Ihre eigenen Buchungen löschen.', 'error')
        return redirect(url_for('meine_buchungen'))
    
    # Prüfe ob Löschen noch möglich ist (außer Admin)
    if not is_admin:
        can_modify, modify_reason = can_modify_booking(booking['date'], booking['period'])
        if not can_modify:
            if is_ajax:
                return jsonify({'success': False, 'message': f'Diese Buchung kann nicht mehr gelöscht werden: {modify_reason}'}), 400
            flash(f'Diese Buchung kann nicht mehr gelöscht werden: {modify_reason}', 'error')
            return redirect(url_for('meine_buchungen'))
    
    # Lösche Buchung
    if delete_booking(booking_id):
        if is_ajax:
            return jsonify({'success': True, 'message': 'Buchung erfolgreich gelöscht.'})
        flash('Buchung erfolgreich gelöscht.', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Buchung konnte nicht gelöscht werden.'}), 500
        flash('Buchung konnte nicht gelöscht werden.', 'error')
    
    return redirect(url_for('meine_buchungen'))

# Route: Admin-Bereich
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    """Admin-Seite für Benutzerverwaltung und Buchungsübersicht"""
    
    if request.method == 'POST':
        # Neue Lehrkraft anlegen
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()
        
        if not username or not password:
            flash('Bitte füllen Sie alle Felder aus.', 'error')
        else:
            user_id = create_user(username, password, 'teacher', email if email else None)
            if user_id:
                flash(f'Lehrkraft {username} erfolgreich angelegt.', 'success')
            else:
                flash('Benutzername existiert bereits.', 'error')
    
    # Hole alle Benutzer
    users = get_all_users()
    
    # Hole ausstehende exklusive Buchungen
    from models import get_pending_exclusive_bookings
    pending_exclusive = get_pending_exclusive_bookings()
    pending_exclusive_display = []
    for booking in pending_exclusive:
        booking_dict = dict(booking)
        students = json.loads(booking_dict['students_json']) if booking_dict.get('students_json') else []
        pending_exclusive_display.append({
            'id': booking_dict['id'],
            'date': booking_dict['date'],
            'weekday': booking_dict['weekday'],
            'period': booking_dict['period'],
            'teacher_email': booking_dict.get('teacher_email'),
            'teacher_name': booking_dict.get('teacher_name', 'N/A'),
            'teacher_class': booking_dict.get('teacher_class', 'N/A'),
            'offer_label': booking_dict['offer_label'],
            'offer_type': booking_dict['offer_type'],
            'students': students,
            'student_count': len(students),
            'notes': booking_dict.get('notes')
        })
    
    # Hole alle Buchungen
    filter_date = request.args.get('filter_date', '')
    if filter_date:
        bookings = get_bookings_by_date(filter_date)
    else:
        bookings = get_all_bookings()
    
    # Konvertiere Buchungen für Anzeige
    bookings_display = []
    for booking in bookings:
        booking_dict = dict(booking)
        students = json.loads(booking_dict['students_json']) if booking_dict.get('students_json') else []
        bookings_display.append({
            'id': booking_dict['id'],
            'date': booking_dict['date'],
            'weekday': booking_dict['weekday'],
            'period': booking_dict['period'],
            'teacher_email': booking_dict['teacher_email'],
            'teacher_name': booking_dict.get('teacher_name', 'N/A'),
            'teacher_class': booking_dict.get('teacher_class', 'N/A'),
            'offer_label': booking_dict['offer_label'],
            'offer_type': booking_dict['offer_type'],
            'students': students,
            'student_count': len(students),
            'notes': booking_dict.get('notes'),
            'is_exclusive': booking_dict.get('is_exclusive', False),
            'is_approved': booking_dict.get('is_approved', True)
        })
    
    return render_template('admin.html',
                         users=users,
                         bookings=bookings_display,
                         pending_exclusive=pending_exclusive_display,
                         filter_date=filter_date)

# Route: Exklusive Buchung genehmigen
@app.route('/admin/approve_exclusive/<int:booking_id>', methods=['POST'])
@admin_required
def approve_exclusive(booking_id):
    """Genehmigt eine exklusive Buchung und entfernt alle anderen Buchungen für denselben Slot"""
    from models import approve_exclusive_booking, get_booking_by_id, Booking
    from database import db
    
    csrf_token = request.form.get('csrf_token', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'
    
    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Ungültiges Sicherheits-Token.'}), 400
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin'))
        
    booking = get_booking_by_id(booking_id)
    if not booking:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Buchung nicht gefunden.'}), 404
        flash('Buchung nicht gefunden.', 'error')
        return redirect(url_for('admin'))
    
    booking_dict = dict(booking)
    date_str = booking_dict['date']
    period = booking_dict['period']
    teacher_email = booking_dict.get('teacher_email')
    teacher_name = booking_dict.get('teacher_name', 'Lehrkraft')
    students = json.loads(booking_dict['students_json']) if booking_dict.get('students_json') else []
    student_name = students[0]['name'] if students else 'Schüler/in'
    
    # Finde alle anderen Buchungen für denselben Slot (nicht-exklusiv oder andere IDs)
    conflicting_bookings = Booking.query.filter(
        Booking.date == date_str,
        Booking.period == period,
        Booking.id != booking_id
    ).all()
    
    # Sammle Daten für E-Mail-Benachrichtigungen VOR dem Löschen
    affected_teachers = []
    for conflict in conflicting_bookings:
        conflict_students = json.loads(conflict.students_json) if conflict.students_json else []
        affected_teachers.append({
            'email': conflict.teacher_email,
            'name': conflict.teacher_name or 'Lehrkraft',
            'booking_info': {
                'date': conflict.date,
                'period': conflict.period,
                'offer_label': conflict.offer_label,
                'students': conflict_students
            }
        })
    
    # Genehmige exklusive Buchung
    success = approve_exclusive_booking(booking_id)
    
    if success:
        # Lösche alle konfliktierenden Buchungen
        removed_count = 0
        for conflict in conflicting_bookings:
            db.session.delete(conflict)
            removed_count += 1
        
        if removed_count > 0:
            db.session.commit()
            print(f"[EXCLUSIVE] {removed_count} konfliktierende Buchungen für {date_str} Stunde {period} entfernt")
        
        # Sende Bestätigungs-E-Mail an den Antragsteller
        if teacher_email:
            from email_service import send_exclusive_approved_email
            send_exclusive_approved_email(
                teacher_email=teacher_email,
                teacher_name=teacher_name,
                student_name=student_name,
                date_str=date_str,
                period=period
            )
        
        # Sende Stornierungs-E-Mails an betroffene Lehrer
        from email_service import send_booking_removed_due_to_exclusive
        for teacher in affected_teachers:
            if teacher['email']:
                try:
                    send_booking_removed_due_to_exclusive(
                        teacher_email=teacher['email'],
                        teacher_name=teacher['name'],
                        booking_info=teacher['booking_info'],
                        exclusive_info={'teacher': teacher_name, 'student': student_name}
                    )
                    print(f"[EXCLUSIVE] Stornierungs-E-Mail an {teacher['email']} gesendet")
                except Exception as e:
                    print(f"[EXCLUSIVE] E-Mail an {teacher['email']} fehlgeschlagen: {e}")
        
        if is_ajax:
            return jsonify({'success': True, 'message': 'Exklusive Buchung genehmigt.'})
            
        if removed_count > 0:
            flash(f'Exklusive Buchung genehmigt. {removed_count} andere Buchung(en) wurden storniert und die Lehrkräfte benachrichtigt.', 'success')
        else:
            flash('Exklusive Buchung wurde genehmigt. Der Slot ist jetzt vollständig reserviert.', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Fehler beim Genehmigen.'}), 500
        flash('Fehler beim Genehmigen der Buchung.', 'error')
    
    return redirect(url_for('admin'))

# Route: Exklusive Buchung ablehnen
@app.route('/admin/reject_exclusive/<int:booking_id>', methods=['POST'])
@admin_required
def reject_exclusive(booking_id):
    """Lehnt eine exklusive Buchung ab (löscht sie)"""
    from models import reject_exclusive_booking, get_booking_by_id
    
    csrf_token = request.form.get('csrf_token', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'
    
    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Ungültiges Sicherheits-Token.'}), 400
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin'))
        
    # Hole Ablehnungsgrund aus dem Formular
    rejection_reason = request.form.get('reason', '').strip()
    
    # Hole Buchungsdetails für E-Mail vor dem Löschen
    booking = get_booking_by_id(booking_id)
    teacher_email = None
    teacher_name = None
    student_name = None
    date_str = None
    period = None
    
    if booking:
        booking_dict = dict(booking)
        teacher_email = booking_dict.get('teacher_email')
        teacher_name = booking_dict.get('teacher_name', 'Lehrkraft')
        students = json.loads(booking_dict['students_json']) if booking_dict.get('students_json') else []
        student_name = students[0]['name'] if students else 'Schüler/in'
        date_str = booking_dict['date']
        period = booking_dict['period']
    
    success = reject_exclusive_booking(booking_id)
    if success:
        # Sende Ablehnungs-E-Mail
        if teacher_email:
            from email_service import send_exclusive_rejected_email
            send_exclusive_rejected_email(
                teacher_email=teacher_email,
                teacher_name=teacher_name,
                student_name=student_name,
                date_str=date_str,
                period=period,
                rejection_reason=rejection_reason
            )
        
        if is_ajax:
            return jsonify({'success': True, 'message': 'Exklusive Buchung erfolgreich abgelehnt.'})
        flash('Exklusive Buchung wurde abgelehnt und gelöscht. Die Lehrkraft wurde benachrichtigt.', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Fehler beim Ablehnen der Buchung.'}), 500
        flash('Fehler beim Ablehnen der Buchung.', 'error')
    
    return redirect(url_for('admin'))

# Route: Buchung erstellen (nur Admin)
@app.route('/admin/create_booking', methods=['GET', 'POST'])
@admin_required
def admin_create_booking():
    """Admin kann Buchungen für beliebige Lehrkräfte erstellen"""
    from models import get_booking_by_id
    
    if request.method == 'POST':
        date_str = request.form.get('date', '').strip()
        
        try:
            period = int(request.form.get('period', 1))
            teacher_id = int(request.form.get('teacher_id', 0))
            num_students = int(request.form.get('num_students', 1))
        except (ValueError, TypeError):
            flash('Ungültige Eingabe für Stunde, Lehrkraft oder Schüleranzahl.', 'error')
            users = get_all_users()
            return render_template('admin_edit_booking.html',
                                 booking=None,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        teacher_name = request.form.get('teacher_name', '').strip()
        teacher_class = request.form.get('teacher_class', '').strip()
        
        if not date_str or not teacher_id or not teacher_name or not teacher_class or num_students < 1 or num_students > 5:
            flash('Bitte füllen Sie alle Pflichtfelder aus und wählen Sie 1-5 Schüler.', 'error')
            users = get_all_users()
            return render_template('admin_edit_booking.html',
                                 booking=None,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        try:
            booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            flash('Ungültiges Datum.', 'error')
            users = get_all_users()
            return render_template('admin_edit_booking.html',
                                 booking=None,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        weekday = booking_date.strftime('%a')
        period_info = get_period_info(weekday, period)
        
        # Prüfe Kapazität vor dem Erstellen der Buchung
        current_students = count_students_for_period(date_str, period)
        available_spots = get_max_students() - current_students
        
        if num_students > available_spots:
            flash(f'Nicht genug Plätze verfügbar. Nur noch {available_spots} Plätze frei.', 'error')
            users = get_all_users()
            return render_template('admin_edit_booking.html',
                                 booking=None,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        students = []
        for i in range(num_students):
            name = request.form.get(f'student_name_{i}', '').strip()
            klasse = request.form.get(f'student_class_{i}', '').strip()
            
            if not name or not klasse:
                flash('Bitte füllen Sie alle Schülerfelder aus.', 'error')
                users = get_all_users()
                return render_template('admin_edit_booking.html',
                                     booking=None,
                                     users=users,
                                     free_modules=get_free_courses(),
                                     period_times=get_period_times())
            
            students.append({'name': name, 'klasse': klasse})
        
        if period_info['type'] == 'frei':
            selected_module = request.form.get('module', '')
            if selected_module not in get_free_courses():
                flash('Bitte wählen Sie ein Modul.', 'error')
                users = get_all_users()
                return render_template('admin_edit_booking.html',
                                     booking=None,
                                     users=users,
                                     free_modules=get_free_courses(),
                                     period_times=get_period_times())
            offer_label = selected_module
        else:
            offer_label = period_info['label']
        
        # Hole optionale Notizen (Admin-Buchungen)
        notes = request.form.get('notes', '').strip()
        
        booking_id = create_booking(
            date=date_str,
            weekday=weekday,
            period=period,
            teacher_id=teacher_id,
            students=students,
            offer_type=period_info['type'],
            offer_label=offer_label,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            notes=notes if notes else None
        )
        
        if booking_id:
            flash(f'Buchung erfolgreich erstellt! {len(students)} Schüler für {offer_label} angemeldet.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Fehler beim Erstellen der Buchung.', 'error')
    
    users = get_all_users()
    return render_template('admin_edit_booking.html',
                         booking=None,
                         users=users,
                         free_modules=get_free_courses(),
                         period_times=get_period_times())

# Route: Buchung bearbeiten (nur Admin)
@app.route('/admin/edit_booking/<int:booking_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_booking(booking_id):
    """Admin kann bestehende Buchungen bearbeiten"""
    from models import get_booking_by_id, update_booking
    
    booking_row = get_booking_by_id(booking_id)
    if not booking_row:
        flash('Buchung nicht gefunden.', 'error')
        return redirect(url_for('admin'))
    
    booking = dict(booking_row)
    
    if request.method == 'POST':
        date_str = request.form.get('date', '').strip()
        
        try:
            period = int(request.form.get('period', 1))
            teacher_id = int(request.form.get('teacher_id', 0))
            num_students = int(request.form.get('num_students', 1))
        except (ValueError, TypeError):
            flash('Ungültige Eingabe für Stunde, Lehrkraft oder Schüleranzahl.', 'error')
            users = get_all_users()
            students = json.loads(booking['students_json']) if booking.get('students_json') else []
            booking_display = dict(booking)
            booking_display['students'] = students
            return render_template('admin_edit_booking.html',
                                 booking=booking_display,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        teacher_name = request.form.get('teacher_name', '').strip()
        teacher_class = request.form.get('teacher_class', '').strip()
        
        if not date_str or not teacher_id or not teacher_name or not teacher_class or num_students < 1 or num_students > 5:
            flash('Bitte füllen Sie alle Pflichtfelder aus und wählen Sie 1-5 Schüler.', 'error')
            users = get_all_users()
            students = json.loads(booking['students_json']) if booking.get('students_json') else []
            booking_display = dict(booking)
            booking_display['students'] = students
            return render_template('admin_edit_booking.html',
                                 booking=booking_display,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        try:
            booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            flash('Ungültiges Datum.', 'error')
            users = get_all_users()
            students = json.loads(booking['students_json']) if booking.get('students_json') else []
            booking_display = dict(booking)
            booking_display['students'] = students
            return render_template('admin_edit_booking.html',
                                 booking=booking_display,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        weekday = booking_date.strftime('%a')
        period_info = get_period_info(weekday, period)
        
        # Prüfe Kapazität: Berechne verfügbare Plätze ohne die aktuelle Buchung
        current_students = count_students_for_period(date_str, period)
        old_booking_students = len(json.loads(booking['students_json']) if booking.get('students_json') else [])
        available_spots = get_max_students() - (current_students - old_booking_students)
        
        if num_students > available_spots:
            flash(f'Nicht genug Plätze verfügbar. Nur noch {available_spots} Plätze frei.', 'error')
            users = get_all_users()
            students = json.loads(booking['students_json']) if booking.get('students_json') else []
            booking_display = dict(booking)
            booking_display['students'] = students
            return render_template('admin_edit_booking.html',
                                 booking=booking_display,
                                 users=users,
                                 free_modules=get_free_courses(),
                                 period_times=get_period_times())
        
        students = []
        for i in range(num_students):
            name = request.form.get(f'student_name_{i}', '').strip()
            klasse = request.form.get(f'student_class_{i}', '').strip()
            
            if not name or not klasse:
                flash('Bitte füllen Sie alle Schülerfelder aus.', 'error')
                users = get_all_users()
                students = json.loads(booking['students_json']) if booking.get('students_json') else []
                booking_display = dict(booking)
                booking_display['students'] = students
                return render_template('admin_edit_booking.html',
                                     booking=booking_display,
                                     users=users,
                                     free_modules=get_free_courses(),
                                     period_times=get_period_times())
            
            students.append({'name': name, 'klasse': klasse})
        
        if period_info['type'] == 'frei':
            selected_module = request.form.get('module', '')
            if selected_module not in get_free_courses():
                flash('Bitte wählen Sie ein Modul.', 'error')
                users = get_all_users()
                students = json.loads(booking['students_json']) if booking.get('students_json') else []
                booking_display = dict(booking)
                booking_display['students'] = students
                return render_template('admin_edit_booking.html',
                                     booking=booking_display,
                                     users=users,
                                     free_modules=get_free_courses(),
                                     period_times=get_period_times())
            offer_label = selected_module
        else:
            offer_label = period_info['label']
        
        # Hole optionale Notizen (Admin kann Notizen bearbeiten)
        notes = request.form.get('notes', '').strip()
        
        if update_booking(
            booking_id=booking_id,
            date=date_str,
            weekday=weekday,
            period=period,
            teacher_id=teacher_id,
            students=students,
            offer_type=period_info['type'],
            offer_label=offer_label,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            notes=notes if notes else None
        ):
            flash(f'Buchung erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Fehler beim Aktualisieren der Buchung.', 'error')
    
    users = get_all_users()
    students = json.loads(booking['students_json']) if booking.get('students_json') else []
    booking_display = dict(booking)
    booking_display['students'] = students
    
    return render_template('admin_edit_booking.html',
                         booking=booking_display,
                         users=users,
                         free_modules=get_free_courses(),
                         period_times=get_period_times())

# Route: Buchung löschen (nur Admin)
@app.route('/admin/delete_booking/<int:booking_id>', methods=['POST'])
@admin_required
def delete_booking_route(booking_id):
    """Löscht eine Buchung"""
    from models import delete_booking
    
    # Lösche Buchung
    if delete_booking(booking_id):
        flash('Buchung erfolgreich gelöscht.', 'success')
    else:
        flash('Buchung konnte nicht gelöscht werden.', 'error')
    
    return redirect(url_for('admin'))

# Route: Slots verwalten (nur Admin)
@app.route('/admin/manage_slots', methods=['GET', 'POST'])
@admin_required
def manage_slots():
    """Admin kann feste Slot-Namen umbenennen"""
    from models import update_slot_name
    
    if request.method == 'POST':
        weekday = request.form.get('weekday')
        period_str = request.form.get('period')
        period = int(period_str) if period_str else 0
        label = request.form.get('label', '').strip()
        
        if weekday and period and label:
            if update_slot_name(weekday, period, label):
                flash(f'Slot-Name erfolgreich aktualisiert!', 'success')
            else:
                flash('Fehler beim Aktualisieren des Slot-Namens.', 'error')
        else:
            flash('Bitte füllen Sie alle Felder aus.', 'error')
        
        return redirect(url_for('manage_slots'))
    
    fixed_slots = []
    weekdays = {
        'Mon': 'Montag',
        'Tue': 'Dienstag', 
        'Wed': 'Mittwoch',
        'Thu': 'Donnerstag',
        'Fri': 'Freitag'
    }
    
    for weekday_code, weekday_name in weekdays.items():
        if weekday_code in get_fixed_offers():
            for period, default_label in get_fixed_offers().get(weekday_code, {}).items():
                period_info = get_period_info(weekday_code, period)
                fixed_slots.append({
                    'weekday_code': weekday_code,
                    'weekday_name': weekday_name,
                    'period': period,
                    'period_time': f"{_get_period_dict(period)['start']} - {_get_period_dict(period)['end']}",
                    'default_label': default_label,
                    'current_label': period_info['label']
                })
    
    return render_template('admin_manage_slots.html', 
                         fixed_slots=fixed_slots)

@app.route('/admin/block_slot', methods=['POST'])
@admin_required
def admin_block_slot():
    """Admin blockiert einen Slot für Beratungsgespräche"""
    from models import block_slot, is_slot_blocked
    
    # CSRF-Token Validierung
    csrf_token = request.form.get('csrf_token', '')
    if not validate_csrf_token(csrf_token):
        flash('Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    date_str = request.form.get('date', '').strip()
    period = request.form.get('period', type=int)
    reason = request.form.get('reason', 'Beratung').strip()
    icon = request.form.get('icon', '🔧').strip()
    
    # Validiere Grund-Länge
    if reason and len(reason) > 200:
        reason = reason[:200]
    
    # Validiere Icon
    allowed_icons = ['🔧', '💬', '📚', '🏖️', '🎉', '🎓', '🤒', '🤝', '💻', '📞', '🚪', '⚠️']
    if icon not in allowed_icons:
        icon = '🔧'
    
    if not date_str or not period:
        flash('Ungültige Slot-Daten.', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        weekday = booking_date.strftime('%a')
    except:
        flash('Ungültiges Datum.', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    if is_slot_blocked(date_str, period):
        flash('Dieser Slot ist bereits blockiert.', 'warning')
    else:
        admin_id = session.get('user_id')
        if block_slot(date_str, weekday, period, admin_id, reason, icon):
            flash(f'Slot erfolgreich für {reason} blockiert.', 'success')
        else:
            flash('Fehler beim Blockieren des Slots.', 'error')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/unblock_slot', methods=['POST'])
@admin_required
def admin_unblock_slot():
    """Admin gibt einen blockierten Slot wieder frei"""
    from models import unblock_slot
    
    # CSRF-Token Validierung
    csrf_token = request.form.get('csrf_token', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'
    
    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Ungültiges Sicherheits-Token.'}), 400
        flash('Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    date_str = request.form.get('date', '').strip()
    period = request.form.get('period', type=int)
    
    if not date_str or not period:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Ungültige Slot-Daten.'}), 400
        flash('Ungültige Slot-Daten.', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    if unblock_slot(date_str, period):
        if is_ajax:
            return jsonify({'success': True, 'message': 'Slot erfolgreich freigegeben.'})
        flash('Slot erfolgreich freigegeben.', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Fehler beim Freigeben des Slots.'}), 500
        flash('Fehler beim Freigeben des Slots.', 'error')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/setup_holidays_2026', methods=['POST'])
@admin_required
def admin_setup_holidays_2026():
    """Legt alle Niedersachsen-Ferien und Feiertage für 2026 automatisch an"""
    from models import bulk_block_slots
    
    # CSRF-Token Validierung
    csrf_token = request.form.get('csrf_token', '')
    if not validate_csrf_token(csrf_token):
        flash('Ungültiges Sicherheits-Token.', 'error')
        return redirect(url_for('admin_bulk_block'))
    
    admin_id = session.get('user_id')
    total_blocked = 0
    total_skipped = 0
    
    # Niedersachsen Schulferien 2026
    holidays_2026 = [
        # Winterferien: 02.02. - 03.02.2026
        ('2026-02-02', '2026-02-03', '❄️ Winterferien', '❄️'),
        # Osterferien: 23.03. - 04.04.2026
        ('2026-03-23', '2026-04-04', '🐣 Osterferien', '🐣'),
        # Pfingstferien: 26.05.2026
        ('2026-05-26', '2026-05-26', '🌸 Pfingstferien', '🌸'),
        # Sommerferien: 16.07. - 26.08.2026
        ('2026-07-16', '2026-08-26', '☀️ Sommerferien', '☀️'),
        # Herbstferien: 12.10. - 24.10.2026
        ('2026-10-12', '2026-10-24', '🍂 Herbstferien', '🍂'),
        # Weihnachtsferien: 23.12.2026 - 06.01.2027
        ('2026-12-23', '2027-01-06', '🎄 Weihnachtsferien', '🎄'),
    ]
    
    # Gesetzliche Feiertage Niedersachsen 2026
    public_holidays_2026 = [
        ('2026-01-01', '2026-01-01', '🎆 Neujahr', '🎆'),
        ('2026-04-03', '2026-04-03', '✝️ Karfreitag', '✝️'),
        ('2026-04-06', '2026-04-06', '✝️ Ostermontag', '✝️'),
        ('2026-05-01', '2026-05-01', '🔧 Tag der Arbeit', '🔧'),
        ('2026-05-14', '2026-05-14', '☁️ Christi Himmelfahrt', '☁️'),
        ('2026-05-25', '2026-05-25', '🕊️ Pfingstmontag', '🕊️'),
        ('2026-10-03', '2026-10-03', '🇩🇪 Tag der Deutschen Einheit', '🇩🇪'),
        ('2026-10-31', '2026-10-31', '⛪ Reformationstag', '⛪'),
        ('2026-12-25', '2026-12-25', '🎄 1. Weihnachtstag', '🎄'),
        ('2026-12-26', '2026-12-26', '🎄 2. Weihnachtstag', '🎄'),
    ]
    
    all_holidays = holidays_2026 + public_holidays_2026
    
    for start_date, end_date, reason, icon in all_holidays:
        result = bulk_block_slots(start_date, end_date, admin_id, reason, icon=icon)
        if result['success']:
            total_blocked += result['blocked_count']
            total_skipped += result['skipped_count']
    
    flash(f'✅ Ferien 2026 angelegt: {total_blocked} Slots blockiert, {total_skipped} bereits vorhanden.', 'success')
    return redirect(url_for('admin_bulk_block'))

@app.route('/admin/bulk_block', methods=['GET', 'POST'])
@admin_required
def admin_bulk_block():
    """Admin kann mehrere Slots auf einmal sperren (z.B. für Ferien)"""
    from models import bulk_block_slots, bulk_unblock_slots, get_all_blocked_slots
    
    blocked_slots = get_all_blocked_slots()
    
    if request.method == 'POST':
        # CSRF-Token Validierung
        csrf_token = request.form.get('csrf_token', '')
        if not validate_csrf_token(csrf_token):
            flash('Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.', 'error')
            return redirect(url_for('admin_bulk_block'))
        
        action = request.form.get('action', 'block')
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        reason = request.form.get('reason', 'Ferien').strip()
        
        # Stunden auswählen (Checkboxen)
        periods = request.form.getlist('periods', type=int)
        if not periods:
            periods = None  # Alle Stunden
        
        # Validierung
        if not start_date or not end_date:
            flash('Bitte Start- und Enddatum angeben.', 'error')
            return redirect(url_for('admin_bulk_block'))
        
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            if start > end:
                flash('Startdatum muss vor dem Enddatum liegen.', 'error')
                return redirect(url_for('admin_bulk_block'))
        except:
            flash('Ungültiges Datumsformat.', 'error')
            return redirect(url_for('admin_bulk_block'))
        
        admin_id = session.get('user_id')
        
        if action == 'block':
            result = bulk_block_slots(start_date, end_date, admin_id, reason, periods)
            if result['success']:
                flash(f"✅ {result['blocked_count']} Slots erfolgreich gesperrt ({result['skipped_count']} bereits gesperrt übersprungen).", 'success')
            else:
                flash(f"Fehler beim Sperren: {result.get('error', 'Unbekannter Fehler')}", 'error')
        elif action == 'unblock':
            result = bulk_unblock_slots(start_date, end_date, periods)
            if result['success']:
                flash(f"✅ {result['unblocked_count']} Slots erfolgreich freigegeben.", 'success')
            else:
                flash(f"Fehler beim Freigeben: {result.get('error', 'Unbekannter Fehler')}", 'error')
        
        return redirect(url_for('admin_bulk_block'))
    
    return render_template('admin_bulk_block.html', blocked_slots=blocked_slots)

# ============================================================================
# Notifications & Server-Sent Events (SSE) Routes
# ============================================================================

# SSE deaktiviert - verursacht Worker-Timeouts in Produktion mit Gunicorn
# @app.route('/notifications/stream')
# @admin_required
# def notifications_stream():
#     """SSE-Endpunkt für Echtzeit-Benachrichtigungen (nur für Admins)"""
#     def event_stream():
#         """Generator für Server-Sent Events"""
#         q = queue.Queue(maxsize=50)
#         
#         with subscribers_lock:
#             notification_subscribers.append(q)
#         
#         try:
#             while True:
#                 try:
#                     message = q.get(timeout=30)
#                     yield f"data: {json.dumps(message)}\n\n"
#                 except queue.Empty:
#                     yield f"data: {json.dumps({'type': 'ping'})}\n\n"
#         finally:
#             with subscribers_lock:
#                 if q in notification_subscribers:
#                     notification_subscribers.remove(q)
#     
#     return Response(event_stream(), mimetype='text/event-stream')

@app.route('/api/notifications/recent', methods=['GET'])
@admin_required
def api_get_recent_notifications():
    """Holt die neuesten Benachrichtigungen"""
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 50)
    
    notifications = get_recent_notifications(recipient_role='admin', limit=limit)
    return jsonify({
        'success': True,
        'notifications': notifications
    })

@app.route('/api/notifications/unread_count', methods=['GET'])
@admin_required
def api_get_unread_count():
    """Holt die Anzahl der ungelesenen Benachrichtigungen"""
    count = get_unread_notification_count(recipient_role='admin')
    return jsonify({
        'success': True,
        'count': count
    })

@app.route('/api/notifications/<int:notification_id>/mark_read', methods=['POST'])
@admin_required
def api_mark_notification_read(notification_id):
    """Markiert eine Benachrichtigung als gelesen"""
    csrf_token = request.json.get('csrf_token', '') if request.json else ''
    if not validate_csrf_token(csrf_token):
        return jsonify({
            'success': False,
            'error': 'Invalid CSRF token'
        }), 403
    
    success = mark_notification_as_read(notification_id)
    return jsonify({
        'success': success
    })

@app.route('/api/notifications/mark_all_read', methods=['POST'])
@admin_required
def api_mark_all_notifications_read():
    """Markiert alle Benachrichtigungen als gelesen"""
    csrf_token = request.json.get('csrf_token', '') if request.json else ''
    if not validate_csrf_token(csrf_token):
        return jsonify({
            'success': False,
            'error': 'Invalid CSRF token'
        }), 403
    
    success = mark_all_notifications_as_read(recipient_role='admin')
    return jsonify({
        'success': success
    })

# ── Admin CMS: Inhalte bearbeiten ────────────────────────────────────────────

@app.route('/admin/cms')
@admin_required
def admin_cms():
    """CMS-Seite für Admin: Login-Texte, Datenschutz, Impressum, Hinweistexte, Demo-Modus"""
    cms = {
        'login_title':      get_config('login_title', ''),
        'login_subtitle':   get_config('login_subtitle', ''),
        'login_notice':     get_config('login_notice', ''),
        'privacy_text':     get_config('cms_privacy_text', ''),
        'imprint_text':     get_config('cms_imprint_text', ''),
        'dashboard_notice': get_config('dashboard_notice', ''),
        'booking_notice':   get_config('booking_notice', ''),
    }
    # DB-URL für Anzeige (maskiert)
    from local_config import get_database_url as _get_db_url
    _raw_db = _get_db_url() or ''
    _db_masked = ''
    if _raw_db:
        try:
            from urllib.parse import urlparse as _up
            _p = _up(_raw_db)
            _db_masked = _raw_db.replace(_p.password, '****') if _p.password else _raw_db
        except Exception:
            _db_masked = _raw_db[:20] + '...' if len(_raw_db) > 20 else _raw_db
    return render_template('admin_cms.html', cms=cms, demo_mode=is_demo_mode(),
                           db_url_masked=_db_masked)


@app.route('/admin/cms/save', methods=['POST'])
@admin_required
def admin_cms_save():
    """Speichert CMS-Inhalte"""
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Ungültiges Sicherheitstoken.', 'error')
        return redirect(url_for('admin_cms'))

    section = request.form.get('section', '')

    if section == 'login':
        from system_config import set_configs
        set_configs({
            'login_title':    request.form.get('login_title', '').strip(),
            'login_subtitle': request.form.get('login_subtitle', '').strip(),
            'login_notice':   request.form.get('login_notice', '').strip(),
        }, category='cms')
        flash('Login-Texte gespeichert.', 'success')

    elif section == 'privacy':
        from system_config import set_config as _sc
        _sc('cms_privacy_text', request.form.get('privacy_text', '').strip(), category='cms')
        flash('Datenschutzerklärung gespeichert.', 'success')

    elif section == 'imprint':
        from system_config import set_config as _sc
        _sc('cms_imprint_text', request.form.get('imprint_text', '').strip(), category='cms')
        flash('Impressum gespeichert.', 'success')

    elif section == 'hints':
        from system_config import set_configs
        set_configs({
            'dashboard_notice': request.form.get('dashboard_notice', '').strip(),
            'booking_notice':   request.form.get('booking_notice', '').strip(),
        }, category='cms')
        flash('Hinweistexte gespeichert.', 'success')

    elif section == 'demo':
        from system_config import set_config as _sc
        enabled = 'demo_mode_enabled' in request.form
        _sc('demo_mode', 'true' if enabled else 'false', category='system')
        flash(f'Demo-Modus {"aktiviert" if enabled else "deaktiviert"}.', 'success')

    elif section == 'database':
        from local_config import set_database_url
        db_url = request.form.get('database_url', '').strip()
        if not db_url:
            flash('Keine URL eingegeben – Datenbank-Konfiguration unverändert.', 'info')
            return redirect(url_for('admin_cms') + '#tab-database')
        # Verbindung testen
        try:
            import sqlalchemy as _sa
            _engine = _sa.create_engine(db_url, connect_args={"connect_timeout": 8})
            with _engine.connect() as _conn:
                _conn.execute(_sa.text('SELECT 1'))
            _engine.dispose()
        except Exception as e:
            flash(f'Verbindungstest fehlgeschlagen: {e}', 'error')
            return redirect(url_for('admin_cms') + '#tab-database')
        set_database_url(db_url)
        flash('Datenbank-URL gespeichert. ✅ Bitte starte die App neu, damit die neue Verbindung aktiv wird.', 'success')
        return redirect(url_for('admin_cms') + '#tab-database')

    return redirect(url_for('admin_cms') + f'#tab-{section}')


# Error-Handler für Production mit Fallback
@app.errorhandler(404)
def not_found_error(error):
    """Handler für 404 Not Found Fehler"""
    try:
        return render_template('errors/404.html'), 404
    except Exception:
        return '<h1>404 - Seite nicht gefunden</h1><p><a href="/">Zur Startseite</a></p>', 404

@app.errorhandler(500)
def internal_error(error):
    """Handler für 500 Internal Server Error"""
    import traceback
    tb = traceback.format_exc()
    print("!!! 500 INTERNAL SERVER ERROR !!!")
    print(tb)
    
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        return render_template('errors/500.html'), 500
    except Exception:
        return '<h1>500 - Interner Serverfehler</h1><p>Bitte versuchen Sie es später erneut.</p>', 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handler für 403 Forbidden Fehler"""
    try:
        return render_template('errors/403.html'), 403
    except Exception:
        return '<h1>403 - Zugriff verweigert</h1><p><a href="/">Zur Startseite</a></p>', 403

# Logging-Konfiguration für Production
import logging
from logging.handlers import RotatingFileHandler
import os

if os.environ.get('FLASK_ENV') == 'production' or not os.environ.get('FLASK_DEBUG'):
    if not os.path.exists('logs'):
        try:
            os.mkdir('logs')
        except OSError:
            pass
    
    try:
        file_handler = RotatingFileHandler('logs/sportoase.log', maxBytes=10240000, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('SportOase Buchungssystem gestartet (Production Mode)')
    except Exception as e:
        print(f"Fehler beim Einrichten des Logging-Handlers: {e}")

if __name__ == '__main__':
    # Starte die Anwendung
    app.run(host='0.0.0.0', port=5000, debug=True)
