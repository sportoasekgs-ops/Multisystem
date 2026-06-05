# Haupt-Anwendungsdatei für das Buchungssystem
# Diese Datei enthält alle Routen (URLs) und die Logik der Webanwendung

import json
import os
import queue
import threading
from datetime import date, datetime, timedelta

import pytz
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

# Flask-App erstellen
app = Flask(__name__)


# Jinja2-Filter: Nachnamen kürzen (Datenschutz)
@app.template_filter("course_emoji")
def course_emoji_filter(label):
    """Gibt das passende Emoji für einen Kursnamen zurück."""
    if not label:
        return "⭐"
    if "Wochenstart" in label:
        return "☀️"
    if "Konflikt" in label or "Deeskalation" in label:
        return "🛡️"
    if "Koordination" in label:
        return "🎯"
    if "Sozial" in label or "Gruppen" in label:
        return "👥"
    if "Mini-Fitness" in label or "Aktivierung" in label:
        return "⚡"
    if "Motorik" in label or "Parcours" in label:
        return "🏃"
    if "Turnen" in label or "Balance" in label:
        return "🤸"
    if "Atem" in label or "Reflexion" in label:
        return "🌬️"
    if "Bodyscan" in label:
        return "🧘"
    if "Ruhe" in label or "Entspannung" in label:
        return "🍃"
    return "⭐"


@app.template_filter("abbreviate_name")
def abbreviate_name_filter(name):
    """Kürzt den Nachnamen auf den ersten Buchstaben + Punkt.
    z.B. 'Max Mustermann' → 'Max M.'
    Leere Namen → '—' (Schüler ohne Namen)
    """
    if not name or not name.strip():
        return "—"
    parts = name.strip().split()
    if len(parts) <= 1:
        return name
    return parts[0] + " " + parts[-1][0] + "."


# Session-Secret aus Umgebungsvariable (MUSS gesetzt sein!)
session_secret = os.environ.get("SESSION_SECRET")
if not session_secret:
    raise RuntimeError(
        "SESSION_SECRET Umgebungsvariable ist nicht gesetzt! "
        "Bitte setzen Sie einen sicheren, zufälligen Wert in den Umgebungsvariablen."
    )
app.secret_key = session_secret
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Cookie-Einstellungen für iFrame-Kompatibilität (IServ Embed)
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True

_iserv_domain_cache = None
_iserv_domain_loaded = False


def invalidate_iserv_domain_cache():
    """Nach CMS-Änderung der IServ-Domain den Prozess-Cache leeren."""
    global _iserv_domain_cache, _iserv_domain_loaded
    _iserv_domain_cache = None
    _iserv_domain_loaded = False


@app.after_request
def add_iframe_headers(response):
    """Erlaubt Einbettung in IServ iFrame"""
    global _iserv_domain_cache, _iserv_domain_loaded
    try:
        if not _iserv_domain_loaded:
            from system_config import get_config

            _iserv_domain_cache = get_config("iserv_domain", "")
            _iserv_domain_loaded = True
        iserv_domain = _iserv_domain_cache or ""
        if iserv_domain:
            origin = f"https://{iserv_domain}"
            response.headers["X-Frame-Options"] = f"ALLOW-FROM {origin}"
            response.headers["Content-Security-Policy"] = (
                f"frame-ancestors 'self' {origin}"
            )
        else:
            response.headers.pop("X-Frame-Options", None)
    except Exception:
        pass
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


def start_background_task(target, *args, **kwargs):
    """Startet einen Hintergrund-Task mit aktivem Flask-App-Kontext."""

    def runner():
        with app.app_context():
            target(*args, **kwargs)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread


# CSRF-Token Generierung und Validierung
import secrets


def generate_csrf_token():
    """Generiert ein CSRF-Token und speichert es in der Session"""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token(token):
    """Validiert das CSRF-Token"""
    return token == session.get("csrf_token")


@app.context_processor
def inject_csrf_token():
    """Macht csrf_token in allen Templates verfügbar"""
    return dict(csrf_token=generate_csrf_token())


@app.context_processor
def inject_period_order():
    """Stunden/Pausen in Anzeigereihenfolge (sort_order), nicht nach interner Nummer."""
    if _BOOTSTRAP_MODE:
        return {}
    try:
        from dynamic_config import get_ordered_period_numbers

        return dict(period_order=get_ordered_period_numbers())
    except Exception:
        return dict(period_order=[])


# Datenbank-Konfiguration
# Reihenfolge: lokale Datei (buchungssystem_local.json) → DATABASE_URL Env-Var
from local_config import get_database_url, is_database_configured, set_database_url

db_uri = get_database_url()


def _trigger_restart():
    """Sendet SIGHUP an den Gunicorn-Master, um alle Worker neu zu starten.
    Funktioniert auf Gunicorn-basierten Linux-Servern.
    """
    import signal
    import subprocess

    try:
        result = subprocess.run(
            ["pgrep", "-f", "gunicorn"], capture_output=True, text=True
        )
        pids = [int(p) for p in result.stdout.strip().split() if p.isdigit()]
        if pids:
            master_pid = min(pids)
            os.kill(master_pid, signal.SIGHUP)
            print(f"[Restart] SIGHUP an Gunicorn-Master PID {master_pid} gesendet.")
    except Exception as e:
        print(f"[Restart] Neustart fehlgeschlagen: {e}")


# ── Bootstrap-Modus: keine DB-URL vorhanden ──────────────────────────────────
_BOOTSTRAP_MODE = not bool(db_uri)

if _BOOTSTRAP_MODE:
    # Minimale Routen zum Eingeben der Datenbank-URL
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def bootstrap_catch_all(path):
        return redirect(url_for("bootstrap_db"))

    @app.route("/bootstrap", methods=["GET", "POST"])
    def bootstrap_db():
        error = None
        if request.method == "POST":
            url = request.form.get("database_url", "").strip()
            if not url:
                error = "Bitte eine Datenbank-URL eingeben."
            else:
                set_database_url(url)
                _trigger_restart()
                return render_template("bootstrap_saved.html")
        return render_template("bootstrap_db.html", error=error)

    @app.route("/bootstrap/ready")
    def bootstrap_ready():
        """Wird vom Warte-Screen abgefragt: gibt 200 zurück wenn die App neu gestartet ist."""
        return "ok", 200

else:
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

# Im Bootstrap-Modus SQLite-In-Memory als Platzhalter, damit db.session
# nie mit "not registered with sqlalchemy instance" crasht.
if _BOOTSTRAP_MODE:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
else:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Importiere zentrale Datenbank-Instanz
from database import db

# db immer mit der App registrieren (auch im Bootstrap-Modus)
db.init_app(app)

# Im Bootstrap-Modus: Tabellen in der SQLite-In-Memory-DB anlegen,
# damit Abfragen (z.B. im Setup-Wizard) nicht mit "no such table" crashen.
if _BOOTSTRAP_MODE:
    with app.app_context():
        from models import (  # noqa: F401
            BlockedSlot,
            Booking,
            Course,
            Notification,
            PasswordResetToken,
            Period,
            SchoolClass,
            SlotName,
            SystemConfig,
            User,
        )

        db.create_all()

# Importiere Modelle und Hilfsfunktionen (nur wenn DB verfügbar)
if not _BOOTSTRAP_MODE:
    from demo_mode import get_demo_bookings_for_week, is_demo_mode
    from dynamic_config import (
        format_period_label,
        get_booking_advance_minutes,
        get_fixed_offers,
        get_free_courses,
        get_max_students,
        get_ordered_period_numbers,
        get_period_times,
        get_school_classes_list,
        is_break_period,
        seed_initial_data,
    )
    from dynamic_config import (
        get_period as _get_period_dict,
    )
    from email_service import send_booking_notification
    from models import (
        Booking,
        User,
        Room,
        change_user_password,
        check_student_double_booking,
        count_students_for_period,
        create_booking,
        create_notification,
        create_user,
        delete_booking,
        get_all_bookings,
        get_all_users,
        get_booking_by_id,
        get_bookings_by_date,
        get_bookings_for_date_period,
        get_bookings_for_week,
        get_or_create_oauth_user,
        get_recent_notifications,
        get_unread_notification_count,
        get_unread_notifications,
        get_user_by_email,
        get_user_by_id,
        get_user_by_username,
        mark_all_notifications_as_read,
        mark_notification_as_read,
        update_booking,
        verify_password,
        get_all_rooms,
        get_room_by_id,
        get_default_room,
        create_room,
        update_room,
        delete_room,
    )

    # IServ OAuth-Integration initialisieren
    from oauth_config import determine_user_role, init_oauth

    oauth_instance, iserv_client = init_oauth(app)

    _registered_iserv_config = {
        "client_id": None,
        "client_secret": None,
        "domain": None,
    }

    def get_iserv_client():
        """Gibt den IServ-Client zurück und reinitialisiert ihn dynamisch bei Änderungen in der DB/Umgebung"""
        global iserv_client, _registered_iserv_config
        from oauth_config import _load_iserv_credentials, reinit_oauth
        try:
            db_client_id, db_client_secret, db_domain = _load_iserv_credentials()
        except Exception:
            db_client_id, db_client_secret, db_domain = "", "", ""
        
        config_changed = (
            db_client_id != _registered_iserv_config["client_id"] or
            db_client_secret != _registered_iserv_config["client_secret"] or
            db_domain != _registered_iserv_config["domain"]
        )
        
        if config_changed or (iserv_client is None and db_client_id and db_client_secret and db_domain):
            if not db_client_id or not db_client_secret or not db_domain:
                iserv_client = None
                _registered_iserv_config = {
                    "client_id": None,
                    "client_secret": None,
                    "domain": None,
                }
            else:
                print(f"[OAuth] Dynamische (Re-)Initialisierung von IServ Client für aktuellen Worker...")
                iserv_client = reinit_oauth(app, oauth_instance)
                _registered_iserv_config = {
                    "client_id": db_client_id,
                    "client_secret": db_client_secret,
                    "domain": db_domain,
                }
                
        return iserv_client


    # System-Konfiguration (Setup-Wizard)
    from system_config import get_branding, get_config, is_setup_complete

    # Datenbanktabellen erstellen (inkl. SystemConfig)
    with app.app_context():
        # Alle Modelle explizit importieren damit db.create_all() sie findet
        from models import (  # noqa: F401
            BlockedSlot,
            Booking,
            Course,
            Notification,
            PasswordResetToken,
            Period,
            SchoolClass,
            SlotName,
            SystemConfig,
            User,
            Room,
        )

        db.create_all()

        # --- Auto-Seeding: Lehrer Test-Benutzer ---
        try:
            from models import User, create_user
            lehrer_user = User.query.filter_by(username="lehrer").first()
            if not lehrer_user:
                print("[SEEDING] Erstelle Test-Lehrer-Benutzer 'lehrer'...")
                create_user("lehrer", "lehrer", "teacher", "lehrer@schule.local")
                print("[SEEDING] Test-Lehrer-Benutzer 'lehrer' erfolgreich erstellt.")
        except Exception as e:
            print(f"[SEEDING] Fehler beim Erstellen des Test-Lehrers: {e}")


        # --- Multi-Room Migration ---
        try:
            from models import Room, Booking, BlockedSlot
            inspector = db.inspect(db.engine)
            
            # 1. Standardraum "Kleine Insel" erzeugen, falls kein Raum existiert
            if db.engine.dialect.has_table(db.engine.connect(), 'rooms'):
                default_room = Room.query.first()
                if not default_room:
                    print("[MIGRATION] Erstelle Standard-Raum 'Kleine Insel'...")
                    default_room = Room(
                        name="Kleine Insel",
                        description="Standardraum",
                        color="#6366f1",
                        icon="🏫",
                        is_active=True,
                        sort_order=0
                    )
                    db.session.add(default_room)
                    db.session.commit()
                    print(f"[MIGRATION] Standard-Raum 'Kleine Insel' mit ID {default_room.id} erstellt.")
            
            # 2. room_id in bookings
            if db.engine.dialect.has_table(db.engine.connect(), 'bookings'):
                cols = [c['name'] for c in inspector.get_columns('bookings')]
                if 'room_id' not in cols:
                    print("[MIGRATION] Füge Spalte 'room_id' zu 'bookings' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("ALTER TABLE bookings ADD COLUMN room_id INTEGER REFERENCES rooms(id)"))
                        conn.commit()
                    
                    # Belege mit Default-Raum (ID 1)
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("UPDATE bookings SET room_id = 1 WHERE room_id IS NULL"))
                        conn.commit()
                    print("[MIGRATION] room_id zu bookings hinzugefügt und auf 1 gesetzt.")

            # 3. room_id in blocked_slots
            if db.engine.dialect.has_table(db.engine.connect(), 'blocked_slots'):
                cols = [c['name'] for c in inspector.get_columns('blocked_slots')]
                if 'room_id' not in cols:
                    print("[MIGRATION] Füge Spalte 'room_id' zu 'blocked_slots' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("ALTER TABLE blocked_slots ADD COLUMN room_id INTEGER REFERENCES rooms(id)"))
                        conn.commit()
                    
                    # Belege mit Default-Raum (ID 1)
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("UPDATE blocked_slots SET room_id = 1 WHERE room_id IS NULL"))
                        conn.commit()
                    print("[MIGRATION] room_id zu blocked_slots hinzugefügt und auf 1 gesetzt.")
        except Exception as e:
            print(f"[MIGRATION] Fehler bei der Multi-Room-Migration: {e}")

        # --- Auto-Migrator: Fehlende Spalten hinzufügen (z.B. für blocked_slots.icon) ---
        try:
            inspector = db.inspect(db.engine)
            if db.engine.dialect.has_table(db.engine.connect(), 'blocked_slots'):
                columns = [col['name'] for col in inspector.get_columns('blocked_slots')]
                if 'icon' not in columns:
                    print("[MIGRATION] Füge fehlende Spalte 'icon' zu 'blocked_slots' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        # SQLite und Postgres unterstützen ADD COLUMN
                        conn.execute(text("ALTER TABLE blocked_slots ADD COLUMN icon VARCHAR(10) DEFAULT '🔧'"))
                        conn.commit()
                    print("[MIGRATION] Spalte erfolgreich hinzugefügt.")
            if db.engine.dialect.has_table(db.engine.connect(), "periods"):
                period_columns = [
                    col["name"] for col in inspector.get_columns("periods")
                ]
                if "period_kind" not in period_columns:
                    print("[MIGRATION] Füge Spalte 'period_kind' zu 'periods' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text

                        conn.execute(
                            text(
                                "ALTER TABLE periods ADD COLUMN period_kind VARCHAR(20) DEFAULT 'lesson'"
                            )
                        )
                        conn.commit()
                if "after_lesson" not in period_columns:
                    print("[MIGRATION] Füge Spalte 'after_lesson' zu 'periods' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text

                        conn.execute(
                            text(
                                "ALTER TABLE periods ADD COLUMN after_lesson INTEGER"
                            )
                        )
                        conn.commit()
        except Exception as e:
            print(f"[MIGRATION] Fehler bei der Auto-Migration: {e}")

        # --- Auto-Migrator: Booking status Spalte hinzufügen ---
        try:
            inspector = db.inspect(db.engine)
            if db.engine.dialect.has_table(db.engine.connect(), 'bookings'):
                booking_columns = [col['name'] for col in inspector.get_columns('bookings')]
                if 'status' not in booking_columns:
                    print("[MIGRATION] Füge Spalte 'status' zu 'bookings' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("ALTER TABLE bookings ADD COLUMN status VARCHAR(20) DEFAULT 'booked'"))
                        conn.commit()
                        conn.execute(text("UPDATE bookings SET status = 'booked' WHERE status IS NULL"))
                        conn.commit()
                    print("[MIGRATION] Spalte 'status' erfolgreich hinzugefügt und initialisiert.")
        except Exception as e:
            print(f"[MIGRATION] Fehler bei der Booking status Migration: {e}")

        # --- Auto-Migrator: Booking admin_reply Spalte hinzufügen ---
        try:
            inspector = db.inspect(db.engine)
            if db.engine.dialect.has_table(db.engine.connect(), 'bookings'):
                booking_columns = [col['name'] for col in inspector.get_columns('bookings')]
                if 'admin_reply' not in booking_columns:
                    print("[MIGRATION] Füge Spalte 'admin_reply' zu 'bookings' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("ALTER TABLE bookings ADD COLUMN admin_reply TEXT"))
                        conn.commit()
                    print("[MIGRATION] Spalte 'admin_reply' erfolgreich hinzugefügt.")
        except Exception as e:
            print(f"[MIGRATION] Fehler bei der Booking admin_reply Migration: {e}")

        # --- Auto-Migrator: Notification recipient_user_id Spalte hinzufügen ---
        try:
            inspector = db.inspect(db.engine)
            if db.engine.dialect.has_table(db.engine.connect(), 'notifications'):
                notification_columns = [col['name'] for col in inspector.get_columns('notifications')]
                if 'recipient_user_id' not in notification_columns:
                    print("[MIGRATION] Füge Spalte 'recipient_user_id' zu 'notifications' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("ALTER TABLE notifications ADD COLUMN recipient_user_id INTEGER REFERENCES users(id)"))
                        conn.commit()
                    print("[MIGRATION] Spalte 'recipient_user_id' erfolgreich hinzugefügt.")
        except Exception as e:
            print(f"[MIGRATION] Fehler bei der Notification recipient_user_id Migration: {e}")

        # --- Auto-Migrator: Booking is_request Spalte hinzufügen ---
        try:
            inspector = db.inspect(db.engine)
            if db.engine.dialect.has_table(db.engine.connect(), 'bookings'):
                booking_columns = [col['name'] for col in inspector.get_columns('bookings')]
                if 'is_request' not in booking_columns:
                    print("[MIGRATION] Füge Spalte 'is_request' zu 'bookings' hinzu...")
                    with db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("ALTER TABLE bookings ADD COLUMN is_request BOOLEAN DEFAULT FALSE"))
                        conn.commit()
                        conn.execute(text("UPDATE bookings SET is_request = FALSE WHERE is_request IS NULL"))
                        conn.commit()
                    print("[MIGRATION] Spalte 'is_request' erfolgreich hinzugefügt.")
        except Exception as e:
            print(f"[MIGRATION] Fehler bei der Booking is_request Migration: {e}")
        # --------------------------------------------------------------------------------

        # Für bestehende Installationen (vor Setup-Wizard-Feature):
        # Setup als abgeschlossen markieren wenn Benutzer UND school_name vorhanden.
        # school_name wird nur im Wizard-Schritt "Allgemeine Daten" gesetzt → nach Factory Reset
        # ist es gelöscht, daher kein versehentliches Auto-Complete nach Reset.
        try:
            from models import User
            from system_config import get_config, set_config

            if get_config("setup_complete") is None:
                user_count = User.query.count()
                school_name = get_config("school_name")
                if user_count > 0 and school_name:
                    set_config("setup_complete", "true", category="system")
                    print(
                        "[SETUP] Bestehende Installation erkannt – Setup als abgeschlossen markiert."
                    )
        except Exception as e:
            print(f"[SETUP] Hinweis: Setup-Check fehlgeschlagen: {e}")

        # Dynamische Konfiguration: Stunden/Kurse/Klassen aus Defaults einseeden
        try:
            seed_initial_data()
        except Exception as e:
            print(f"[DynConfig] Seeding beim Start fehlgeschlagen: {e}")

        # Initialisiere registrierte IServ-Konfiguration für get_iserv_client()
        try:
            from oauth_config import _load_iserv_credentials
            db_client_id, db_client_secret, db_domain = _load_iserv_credentials()
            _registered_iserv_config = {
                "client_id": db_client_id,
                "client_secret": db_client_secret,
                "domain": db_domain,
            }
        except Exception:
            pass

# Setup-Wizard Blueprint registrieren
from setup import setup_bp

app.register_blueprint(setup_bp)

# Admin-Blueprint für dynamische Konfiguration (Stunden/Kurse/Klassen)
from admin_dynamic import admin_dyn_bp

app.register_blueprint(admin_dyn_bp)


# ── Error Handlers ──────────────────────────────────────────────────────────
@app.errorhandler(404)
def page_not_found(e):
    return render_template("errors/404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("errors/500.html"), 500


# ── before_request: Setup-Check ──────────────────────────────────────────────
@app.before_request
def check_setup():
    """Leitet zum Setup-Wizard weiter, wenn das System noch nicht eingerichtet ist."""
    # Im Bootstrap-Modus (keine DB konfiguriert): kein Setup-Check nötig,
    # bootstrap_catch_all leitet alle Nicht-Setup-Routen zu /bootstrap weiter.
    if _BOOTSTRAP_MODE:
        return None
    # Routen, die auch ohne abgeschlossenes Setup erreichbar sein müssen
    _SETUP_BYPASS = {
        "static",
        "login",
        "logout",
        "oauth_login",
        "oauth_callback",
        "bootstrap_db",
        "forgot_password",
        "reset_password",
    }
    if request.endpoint and (
        request.endpoint.startswith("setup.") or request.endpoint in _SETUP_BYPASS
    ):
        return None
    # Wenn Setup noch nicht abgeschlossen → Wizard aufrufen
    try:
        if not is_setup_complete():
            return redirect(url_for("setup.index"))
    except Exception:
        # DB noch nicht bereit – Setup-Seite zeigen
        return redirect(url_for("setup.index"))
    return None


# ── Branding-Kontext für alle Templates ─────────────────────────────────────


def _hex_to_rgb(hex_color):
    """Konvertiert einen Hex-Farbwert in 'R, G, B' (kommagetrennt) und 'R G B' (leerzeichengetrennt)."""
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}", f"{r} {g} {b}"
    except Exception:
        return "233, 30, 99", "233 30 99"


def _resolve_logo_url(filename, default=""):
    """Gibt den URL-Pfad zur Logo-Datei zurück (uploads/ oder static root).
    Gibt '' zurück wenn kein Logo konfiguriert ist."""
    if not filename:
        filename = default
    if not filename:
        return ""
    if filename.startswith("data:"):
        return filename
    uploads_path = os.path.join("static", "uploads", filename)
    if os.path.exists(uploads_path):
        return f"/static/uploads/{filename}"
    static_path = os.path.join("static", filename)
    if os.path.exists(static_path):
        return f"/static/{filename}"
    return ""


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
            "school_name": "",
            "school_subtitle": "Buchungssystem",
            "primary_color": "#E91E63",
            "secondary_color": "#C2185B",
            "logo_filename": "",
            "favicon_filename": "",
            "background_color": "#fce4ec",
        }

    primary = branding.get("primary_color", "#E91E63")
    primary_rgb_comma, primary_rgb_space = _hex_to_rgb(primary)

    def _cfg(key, default=""):
        try:
            from system_config import get_config as _gc

            return _gc(key, default)
        except Exception:
            return default

    extra = {
        "logo_url": _resolve_logo_url(branding.get("logo_filename", "")),
        "favicon_url": _resolve_logo_url(branding.get("favicon_filename", "")),
        "primary_rgb": primary_rgb_comma,
        "primary_rgb_space": primary_rgb_space,
        "cms_privacy_text": _cfg("cms_privacy_text"),
        "cms_imprint_text": _cfg("cms_imprint_text"),
        "dashboard_notice": _cfg("dashboard_notice"),
        "booking_notice": _cfg("booking_notice"),
        "contact_name": _cfg("contact_name"),
        "contact_email": _cfg("contact_email"),
        "contact_phone": _cfg("contact_phone"),
        "contact_text": _cfg("contact_text"),
        "font_size_base": _cfg("font_size_base", "100"),
        "font_size_headings": _cfg("font_size_headings", "100"),
        "font_size_table": _cfg("font_size_table", "100"),
        "font_size_widgets": _cfg("font_size_widgets", "100"),
    }
    return dict(branding=branding, **branding, **extra)


@app.context_processor
def inject_dynamic_config():
    """Macht max_students global in allen Templates verfügbar."""
    try:
        ms = get_max_students()
    except Exception:
        ms = 5
    return dict(max_students=ms)


ADMIN_THEME_IDS = frozenset({"classic", "minimal", "slotra2", "slotra-reloaded", "iserv"})


def _resolve_admin_theme():
    """Gespeichertes Seiten-Design aus der Datenbank (systemweit)."""
    from system_config import get_config

    theme = get_config("admin_theme", "classic")
    return theme if theme in ADMIN_THEME_IDS else "classic"


@app.context_processor
def inject_app_theme():
    return dict(admin_theme=_resolve_admin_theme())


# Hilfsfunktion: Zeitzone Europe/Berlin
def get_berlin_tz():
    """Gibt die Zeitzone Europe/Berlin zurück"""
    return pytz.timezone("Europe/Berlin")


# Hilfsfunktion: Prüft, ob Benutzer eingeloggt ist
def login_required(f):
    """Decorator-Funktion: Schützt Routen, sodass nur eingeloggte Benutzer darauf zugreifen können"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bitte melden Sie sich an.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# Hilfsfunktion: Prüft, ob Benutzer Admin ist
def admin_required(f):
    """Decorator-Funktion: Schützt Routen, sodass nur Admins darauf zugreifen können"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bitte melden Sie sich an.", "error")
            return redirect(url_for("login"))
        user = get_user_by_id(session["user_id"])
        if not user or user["role"] != "admin":
            flash("Zugriff verweigert. Nur Admins haben Zugriff.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated_function


# Hilfsfunktion: Gibt Informationen über eine Stunde zurück
def get_period_info(weekday, period, fixed_offers=None):
    """
    Gibt Informationen über eine Stunde zurück (fest/frei, Bezeichnung)
    weekday: z.B. "Mon", "Tue", ...
    period: interne Slot-Nummer (Unterricht oder große Pause)
    """
    from models import get_custom_slot_name

    if is_break_period(period):
        pinfo = _get_period_dict(period)
        return {"type": "pause", "label": pinfo.get("name", "Große Pause")}

    if fixed_offers is None:
        fixed_offers = get_fixed_offers()
    if weekday in fixed_offers and period in fixed_offers[weekday]:
        custom_label = get_custom_slot_name(weekday, period)
        label = custom_label if custom_label else fixed_offers[weekday][period]
        return {"type": "fest", "label": label}
    else:
        return {"type": "frei", "label": "Freie Wahl"}


# Hilfsfunktion: Prüft, ob ein Datum in der Vergangenheit liegt
def is_past_date(check_date, period=None):
    """
    Prüft, ob ein Datum (und optional eine Stunde) in der Vergangenheit liegt
    """
    berlin_tz = get_berlin_tz()
    now = datetime.now(berlin_tz)

    if period is not None:
        # Prüfe mit spezifischer Stunde
        period_start_time = _get_period_dict(period)["start"]
        hour, minute = map(int, period_start_time.split(":"))
        period_datetime = berlin_tz.localize(
            datetime.combine(check_date, datetime.min.time()).replace(
                hour=hour, minute=minute
            )
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
    period_start_time = _get_period_dict(period)["start"]
    hour, minute = map(int, period_start_time.split(":"))

    # Kombiniere Datum und Zeit
    period_datetime = berlin_tz.localize(
        datetime.combine(booking_date, datetime.min.time()).replace(
            hour=hour, minute=minute
        )
    )

    # Berechne Zeitdifferenz
    time_diff = period_datetime - now
    advance_mins = get_booking_advance_minutes()

    if time_diff.total_seconds() < advance_mins * 60:
        return (
            False,
            f"Buchungen sind nur bis {advance_mins} Minuten vor Stundenbeginn möglich.",
        )

    return True, None


# Route: Homepage (Marketing-Website)
@app.route("/homepage")
def redirect_homepage():
    return redirect(url_for("serve_homepage"))

@app.route("/homepage/")
@app.route("/homepage/<path:filename>")
def serve_homepage(filename="index.html"):
    from flask import send_from_directory
    return send_from_directory("homepage", filename)


# Route: Startseite
@app.route("/")
def index():
    """Startseite - leitet zum Dashboard oder der Login-Seite weiter"""
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# Route: Direkter IServ-Embed Login (für iFrame-Integration)
@app.route("/iserv/embed")
def iserv_embed_login():
    """
    Direkter Login für IServ-Embed (iFrame) Integration.
    IServ sendet Benutzer-Informationen über URL-Parameter:
    - %user% → user Parameter
    - %email% → email Parameter
    - %domain% → domain Parameter (zur Verifizierung)

    Sicherheit:
    - Nur konfigurierte E-Mail-Domain
    - Nur bereits registrierte Benutzer (neue müssen OAuth nutzen)
    - Signiertes Token über ISERV_EMBED_SECRET ist Pflicht
    """
    import hashlib
    import hmac
    import time

    from oauth_config import get_allowed_email_domain

    user = request.args.get("user", "").strip()
    email = request.args.get("email", "").strip().lower()
    domain = request.args.get("domain", "").strip().lower()
    token = request.args.get("token", "").strip()
    timestamp = request.args.get("ts", "").strip()
    allowed_domain = get_allowed_email_domain()

    # Debug-Log
    print(f"🔐 IServ Embed Versuch: user={user}, email={email}, domain={domain}")

    # Prüfe ob alle Parameter vorhanden sind
    if not user or not email or not domain:
        flash("Ungültige IServ-Anmeldung.", "error")
        return render_template("login.html")

    # Prüfe ob E-Mail zur erlaubten Schule gehört
    if (
        not allowed_domain
        or "@" not in email
        or not email.endswith(f"@{allowed_domain}")
    ):
        flash(
            f"Nur E-Mail-Adressen der konfigurierten Domain @{allowed_domain or 'schule.de'} sind erlaubt.",
            "error",
        )
        return render_template("login.html")

    if domain != allowed_domain:
        print(f"⚠️ IServ Embed: Ungültige Domain {domain} für {email}")
        flash("Ungültige IServ-Domain.", "error")
        return render_template("login.html")

    # HMAC-Token Validierung ist Pflicht, sonst ist der Embed-Login deaktiviert
    embed_secret = os.environ.get("ISERV_EMBED_SECRET", "").strip()
    if not embed_secret:
        print("⚠️ IServ Embed: ISERV_EMBED_SECRET fehlt – Route ist deaktiviert")
        flash("IServ-Embed-Login ist nicht aktiviert.", "error")
        return render_template("login.html")

    if not token or not timestamp:
        print(f"⚠️ IServ Embed: Token fehlt für {email}")
        flash("Ungültige Anmeldung (Token fehlt).", "error")
        return render_template("login.html")

    # Prüfe Zeitstempel (max 5 Minuten alt)
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            print(f"⚠️ IServ Embed: Token abgelaufen für {email}")
            flash("Anmeldung abgelaufen. Bitte erneut versuchen.", "error")
            return render_template("login.html")
    except ValueError:
        flash("Ungültige Anmeldung.", "error")
        return render_template("login.html")

    # Validiere HMAC
    expected = hmac.new(
        embed_secret.encode(), f"{email}:{timestamp}".encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(token, expected):
        print(f"⚠️ IServ Embed: Ungültiger Token für {email}")
        flash("Ungültige Anmeldung.", "error")
        return render_template("login.html")

    # Hole bestehenden Benutzer aus der Datenbank
    existing_user = get_user_by_email(email)

    if existing_user:
        # Benutzer existiert bereits - direkt einloggen
        session.clear()
        session["user_id"] = existing_user["id"]
        session["user_username"] = existing_user["username"]
        session["user_email"] = existing_user["email"]
        session["user_role"] = existing_user["role"]

        print(f"🔐 IServ Embed Login: {email} (bestehender Benutzer)")
        return redirect(url_for("dashboard"))
    else:
        # Neuer Benutzer - muss sich erst über OAuth registrieren
        flash('Bitte melden Sie sich einmalig über "Mit IServ anmelden" an.', "info")
        return render_template("login.html")


# Route: Login-Seite (nur IServ-Button)
@app.route("/login")
def login():
    """Login-Seite - zeigt nur IServ-Login-Button, mit CMS-Texten"""
    try:
        from system_config import get_config as _get_config

        login_title = _get_config("login_title", "")
        login_subtitle = _get_config("login_subtitle", "")
        login_notice = _get_config("login_notice", "")
    except Exception:
        login_title = login_subtitle = login_notice = ""
    return render_template(
        "login.html",
        login_title=login_title,
        login_subtitle=login_subtitle,
        login_notice=login_notice,
    )


# Route: Demo-Login (Gast / Admin)
@app.route("/login/demo")
def login_demo():
    """Erlaubt einen schnellen Demo-Login im Demo-Modus"""
    if not is_demo_mode():
        flash("Der Demo-Modus ist zurzeit nicht aktiv.", "error")
        return redirect(url_for("login"))

    role = request.args.get("role", "teacher")
    if role == "admin":
        session.clear()
        session["user_id"] = -2
        session["user_username"] = "demo_admin"
        session["user_email"] = "demo.admin@example.com"
        session["user_role"] = "admin"
        flash("Als Demo-Admin eingeloggt.", "success")
    else:
        session.clear()
        session["user_id"] = -1
        session["user_username"] = "demo_teacher"
        session["user_email"] = "demo.teacher@example.com"
        session["user_role"] = "teacher"
        flash("Als Demo-Lehrkraft eingeloggt.", "success")

    return redirect(url_for("dashboard"))


# Route: Lokaler Admin-Login (für Tests ohne IServ)
@app.route("/login/local", methods=["POST"])
def login_local():
    """Lokaler Admin-Login mit Benutzername und Passwort (nur für Admins)"""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Bitte Benutzername und Passwort eingeben.", "error")
        return redirect(url_for("login"))

    user = get_user_by_username(username)
    if not user:
        flash("Ungültige Anmeldedaten.", "error")
        return redirect(url_for("login"))

    # Erlaube lokalen Login für Admins und Lehrkräfte
    if user["role"] not in ["admin", "teacher"]:
        flash("Lokaler Login ist nur für Administratoren und Lehrkräfte verfügbar.", "error")
        return redirect(url_for("login"))

    user_obj = User.query.filter_by(username=username).first()
    if (
        not user_obj
        or not user_obj.password_hash
        or not user_obj.check_password(password)
    ):
        flash("Ungültige Anmeldedaten.", "error")
        return redirect(url_for("login"))

    session.clear()
    session["user_id"] = user["id"]
    session["user_username"] = user["username"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]

    flash(f"Willkommen, {username}! (Lokaler Login)", "success")
    return redirect(url_for("dashboard"))


# Route: Passwort vergessen (GET = Formular, POST = Token senden)
@app.route("/login/forgot", methods=["GET", "POST"])
def forgot_password():
    """Passwort-Reset-Anfrage für lokale Admin-Accounts"""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        if not identifier:
            flash("Bitte Benutzername oder E-Mail eingeben.", "error")
            return redirect(url_for("forgot_password"))

        import secrets
        from datetime import datetime, timedelta

        from models import PasswordResetToken

        # Suche nach Username oder E-Mail
        user = (
            User.query.filter(
                (User.username == identifier) | (User.email == identifier)
            )
            .filter_by(role="admin")
            .first()
        )

        # Sicherheitshinweis: immer gleiche Meldung zeigen (kein User-Enumeration)
        success_msg = (
            "Wenn ein Admin-Account mit diesem Benutzernamen oder dieser E-Mail existiert "
            "und eine E-Mail-Adresse hinterlegt ist, wurde ein Reset-Link verschickt."
        )

        if user and user.email:
            # Alte, nicht verwendete Token für diesen User löschen
            PasswordResetToken.query.filter_by(user_id=user.id, used=False).delete()
            db.session.flush()

            token_str = secrets.token_urlsafe(48)
            token = PasswordResetToken(
                user_id=user.id,
                token=token_str,
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.session.add(token)
            db.session.commit()

            reset_url = url_for("reset_password", token=token_str, _external=True)
            try:
                from email_service import send_password_reset_email

                send_password_reset_email(user.email, user.username, reset_url)
            except Exception as e:
                app.logger.warning(f"[RESET] E-Mail-Versand fehlgeschlagen: {e}")

        flash(success_msg, "info")
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


# Route: Passwort zurücksetzen via Token (GET = neues Passwort Formular, POST = speichern)
@app.route("/login/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Passwort-Reset via Token"""
    from datetime import datetime

    from models import PasswordResetToken

    tok = PasswordResetToken.query.filter_by(token=token, used=False).first()

    if not tok or tok.expires_at < datetime.utcnow():
        flash(
            "Dieser Reset-Link ist ungültig oder abgelaufen. Bitte erneut anfordern.",
            "error",
        )
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        pw1 = request.form.get("password", "")
        pw2 = request.form.get("password2", "")

        if len(pw1) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "error")
            return render_template("reset_password.html", token=token)
        if pw1 != pw2:
            flash("Die Passwörter stimmen nicht überein.", "error")
            return render_template("reset_password.html", token=token)

        user = User.query.get(tok.user_id)
        if not user:
            flash("Benutzer nicht gefunden.", "error")
            return redirect(url_for("login"))

        user.set_password(pw1)
        tok.used = True
        db.session.commit()

        app.logger.info(
            f"[RESET] Passwort für Admin '{user.username}' erfolgreich zurückgesetzt."
        )
        flash(
            "Passwort erfolgreich geändert! Du kannst dich jetzt anmelden.", "success"
        )
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


# Route: IServ SSO Login initiieren
@app.route("/login/iserv")
def login_iserv():
    """Startet den IServ OAuth2-Login-Flow"""
    client = get_iserv_client()
    if not client:
        flash(
            "IServ-Login ist nicht konfiguriert. Bitte ISERV_CLIENT_ID und ISERV_CLIENT_SECRET in den Umgebungsvariablen setzen.",
            "error",
        )
        return redirect(url_for("login"))

    try:
        scheme = "https"
        if "localhost" in request.host or "127.0.0.1" in request.host:
            scheme = "http"
        redirect_uri = url_for("oauth_callback", _external=True, _scheme=scheme)
        print(f"🔐 IServ OAuth: Starte Login, Redirect URI: {redirect_uri}")
        return client.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"❌ IServ OAuth Fehler: {e}")
        flash(f"Fehler beim Starten des IServ-Logins: {str(e)}", "error")
        return redirect(url_for("login"))


# Route: OAuth Callback von IServ
@app.route("/oauth/callback")
def oauth_callback():
    """Callback-Route für IServ OAuth2"""
    client = get_iserv_client()
    if not client:
        flash("IServ-Login ist nicht konfiguriert.", "error")
        return redirect(url_for("login"))

    try:
        scheme = "https"
        if "localhost" in request.host or "127.0.0.1" in request.host:
            scheme = "http"
        redirect_uri = url_for("oauth_callback", _external=True, _scheme=scheme)
        token = client.authorize_access_token(redirect_uri=redirect_uri)

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
        if "roles" in token:
            print(f"\n📋 ROLES IM TOKEN: {token['roles']}")
        if "groups" in token:
            print(f"\n👥 GROUPS IM TOKEN: {token['groups']}")

        # Userinfo aus Token oder separat abrufen
        userinfo = token.get("userinfo")
        print(f"\n📋 USERINFO AUS TOKEN: {'Ja' if userinfo else 'Nein'}")

        if not userinfo:
            print("   → Rufe userinfo separat ab...")
            userinfo = client.userinfo(token=token)

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

        email = userinfo.get("email")
        sub = userinfo.get("sub")
        name = userinfo.get("name", email)

        print(f"\n👤 BENUTZER-DETAILS:")
        print(f"   E-Mail: {email}")
        print(f"   Sub-ID: {sub}")
        print(f"   Name: {name}")

        if not email or not sub:
            print("❌ FEHLER: E-Mail oder Sub-ID fehlt!")
            flash("Fehler beim Abrufen der Benutzerdaten von IServ.", "error")
            return redirect(url_for("login"))

        # Prüfe auch ob Token selbst Rollen/Gruppen enthält und füge sie zu userinfo hinzu
        for claim_key in ("roles", "groups", "iserv:roles", "iserv:groups"):
            if claim_key in token and claim_key not in userinfo:
                userinfo[claim_key] = token[claim_key]
                print(
                    f"\n   → Claim aus Token übernommen ({claim_key}): {token[claim_key]}"
                )

        # determine_user_role gibt jetzt (role, iserv_group) zurück
        role, iserv_group = determine_user_role(userinfo)

        print(f"\n🎯 ROLLENZUWEISUNG:")
        print(f"   App-Rolle: {role}")
        print(f"   IServ-Gruppe: {iserv_group}")
        print("=" * 80)

        # Prüfe ob Benutzer Zugang hat (nur Lehrer, Mitarbeitende, Administrator)
        if role is None:
            # Zeige detaillierte Fehlermeldung mit Hinweis auf IServ-Konfiguration
            error_msg = f"Zugang verweigert für {email}. "

            # Prüfe ob überhaupt Rollen-/Gruppen-Claims vorhanden sind
            has_roles = any(userinfo.get(key) for key in ("roles", "iserv:roles"))
            has_groups = any(userinfo.get(key) for key in ("groups", "iserv:groups"))

            if not has_roles and not has_groups:
                error_msg += "IServ liefert keine Rollen/Gruppen. Bitte prüfen Sie die OAuth-Konfiguration in IServ (Scopes je nach Version: roles/groups oder iserv:roles/iserv:groups)."
                print(f"\n⚠️ WICHTIG: Keine Rollen/Gruppen von IServ erhalten!")
                print(
                    f"   → Prüfen Sie in IServ unter: Admin → Single-Sign-On → App bearbeiten"
                )
                print(
                    "   → Stellen Sie sicher, dass Rollen- und Gruppen-Scopes aktiviert sind "
                    "(je nach IServ-Version: roles/groups oder iserv:roles/iserv:groups)!"
                )
            else:
                error_msg += "Keine berechtigte Rolle gefunden. Nur Schulleitung, Lehrer und Mitarbeitende haben Zugang."

            flash(error_msg, "error")
            print(f"❌ Zugang verweigert für: {email}")
            return redirect(url_for("login"))

        # Verwende E-Mail direkt als Username für OAuth-Benutzer
        user = get_or_create_oauth_user(
            email=email, username=email, oauth_provider="iserv", oauth_id=sub, role=role
        )

        if not user:
            flash("Fehler beim Erstellen des Benutzers.", "error")
            return redirect(url_for("login"))

        # WICHTIG: Session komplett leeren, um OAuth-Token/userinfo zu entfernen
        session.clear()

        # Nur die wesentlichen Benutzerdaten speichern
        session["user_id"] = user["id"]
        session["user_username"] = user["username"]
        session["user_email"] = user["email"]
        session["user_role"] = user["role"]

        print(f"\n✅ LOGIN ERFOLGREICH: {email} → Rolle: {role}")
        flash(f"Willkommen, {name}!", "success")
        return redirect(url_for("dashboard"))

    except Exception as e:
        import traceback

        print(f"\n❌ OAUTH FEHLER:")
        print(f"   Exception: {e}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        flash("Fehler beim IServ-Login. Bitte versuchen Sie es erneut.", "error")
        return redirect(url_for("login"))


# Route: Logout
@app.route("/logout")
def logout():
    """Meldet den Benutzer ab"""
    session.clear()
    flash("Sie wurden abgemeldet.", "info")
    return redirect(url_for("login"))


# Route: OAuth Debug - Zeigt Rollen/Gruppen-Daten von IServ
@app.route("/oauth/debug")
def oauth_debug():
    """
    Debug-Route: Zeigt die OAuth-Daten von IServ (nur für Admins sichtbar).
    Nützlich um zu sehen, welche Rollen/Gruppen IServ übergibt.
    """
    if "user_id" not in session:
        flash("Bitte melden Sie sich an.", "error")
        return redirect(url_for("login"))

    user = get_user_by_id(session["user_id"])
    if not user or user["role"] != "admin":
        flash("Nur für Administratoren zugänglich.", "error")
        return redirect(url_for("dashboard"))

    return (
        """
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <title>OAuth Debug</title>
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
            <p><strong>User ID:</strong> """
        + str(session.get("user_id", "N/A"))
        + """</p>
            <p><strong>Username:</strong> """
        + str(session.get("user_username", "N/A"))
        + """</p>
            <p><strong>E-Mail:</strong> """
        + str(session.get("user_email", "N/A"))
        + """</p>
            <p><strong>Rolle:</strong> """
        + str(session.get("user_role", "N/A"))
        + """</p>
        </div>

        <div class="card">
            <h2>IServ OAuth Konfiguration</h2>
            <p><strong>Angeforderte Scopes:</strong> <code>openid profile email</code> plus Rollen/Gruppen-Scopes (<code>roles groups</code> oder <code>iserv:roles iserv:groups</code>).</p>
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
                <li>Öffnen Sie die OAuth-App in IServ</li>
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
    """
    )


# Route: Passwort ändern
@app.route("/change_password", methods=["GET", "POST"])
@admin_required
def change_password():
    """Ermöglicht Admins Passwörter zu ändern"""
    if request.method == "POST":
        # CSRF-Token Validierung
        csrf_token = request.form.get("csrf_token", "")
        if not validate_csrf_token(csrf_token):
            flash(
                "Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error"
            )
            return redirect(url_for("change_password"))

        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validierung
        if not old_password or not new_password or not confirm_password:
            flash("Bitte füllen Sie alle Felder aus.", "error")
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            flash("Die neuen Passwörter stimmen nicht überein.", "error")
            return redirect(url_for("change_password"))

        if len(new_password) < 6:
            flash("Das neue Passwort muss mindestens 6 Zeichen lang sein.", "error")
            return redirect(url_for("change_password"))

        # Passwort ändern
        result = change_user_password(session["user_id"], old_password, new_password)

        if result["success"]:
            flash(result["message"], "success")
            return redirect(url_for("dashboard"))
        else:
            flash(result["error"], "error")
            return redirect(url_for("change_password"))

    return render_template("change_password.html")


# Route: Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    """Hauptseite - zeigt Wochenplan und Buchungsmöglichkeiten"""
    # Hole aktuelles Datum oder gewähltes Datum
    date_param = request.args.get("date")
    berlin_now = datetime.now(get_berlin_tz())

    if date_param:
        try:
            selected_date = datetime.strptime(date_param, "%Y-%m-%d").date()
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
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    # Wochentag ermitteln (Mon, Tue, ...)
    weekday = selected_date.strftime("%a")
    weekday_name = selected_date.strftime("%A")  # Ausgeschriebener Name

    # Hole gewählten Raum und alle aktiven Räume
    from models import Booking, get_blocked_slot, is_holiday_blocked_reason, is_slot_blocked, get_all_rooms, get_room_by_id, get_default_room

    room_id = request.args.get("room", type=int)
    all_rooms = get_all_rooms(active_only=True)
    
    # Fallback zum Standard-Raum
    default_room = get_default_room()
    current_room = None
    if room_id:
        current_room = get_room_by_id(room_id)
    if not current_room:
        current_room = default_room
        if current_room:
            room_id = current_room.id
        else:
            room_id = 1

    # Deutsche Wochentagsnamen
    weekday_names_de = {
        "Monday": "Montag",
        "Tuesday": "Dienstag",
        "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag",
        "Friday": "Freitag",
        "Saturday": "Samstag",
        "Sunday": "Sonntag",
    }
    weekday_name_de = weekday_names_de.get(weekday_name, weekday_name)

    # Erstelle Stundenplan für den Tag
    from models import Booking, get_blocked_slot, is_holiday_blocked_reason, is_slot_blocked

    period_times = get_period_times()
    period_keys = get_ordered_period_numbers()
    fixed_offers = get_fixed_offers()
    max_students = current_room.max_students if (current_room and current_room.max_students) else get_max_students()

    student_counts_today = {}
    for booking in Booking.query.filter_by(date=selected_date_str, room_id=room_id, is_approved=True).filter(Booking.status != 'no_show').all():
        students = (
            json.loads(booking.students_json) if booking.students_json else []
        )
        student_counts_today[booking.period] = (
            student_counts_today.get(booking.period, 0) + len(students)
        )

    schedule = []
    for period in period_keys:
        period_info = get_period_info(weekday, period, fixed_offers=fixed_offers)
        student_count = student_counts_today.get(period, 0)
        available = max_students - student_count

        # Prüfe, ob Slot blockiert ist
        blocked_slot = get_blocked_slot(selected_date_str, period, room_id=room_id)
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

        pt = period_times[period]
        schedule.append(
            {
                "period": period,
                "period_label": format_period_label(period),
                "time": f"{pt['start']} - {pt['end']}",
                "type": period_info["type"],
                "label": period_info["label"],
                "booked": student_count,
                "available": available,
                "can_book": can_book
                and available > 0
                and not is_blocked
                and not is_past
                and not is_weekend,
                "time_message": time_message,
                "blocked": blocked_slot,
                "blocked_reason": blocked_slot.get("reason", "Beratung")
                if blocked_slot
                else None,
                "blocked_icon": blocked_slot.get("icon", "🔧")
                if blocked_slot
                else None,
                "is_past": is_past,
                "is_weekend": is_weekend,
            }
        )

    # Erstelle Wochenübersicht (Montag-Freitag) mit Buchungsdaten
    from models import (
        get_blocked_slots_for_week,
        get_bookings_for_week,
        is_slot_blocked,
    )

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
    week_bookings = get_bookings_for_week(
        monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d"), room_id=room_id
    )

    # Im Demo-Modus: Fake-Buchungen hinzufügen
    if is_demo_mode():
        demo_bookings = get_demo_bookings_for_week(
            monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d")
        )
        week_bookings = list(week_bookings) + demo_bookings

    # Hole alle blockierten Slots für diese Woche
    blocked_slots = get_blocked_slots_for_week(
        monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d"), room_id=room_id
    )

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

        students = (
            json.loads(booking_dict["students_json"])
            if booking_dict.get("students_json")
            else []
        )
        booking_info = {
            "teacher_name": booking_dict.get("teacher_name", "N/A"),
            "teacher_class": booking_dict.get("teacher_class", "N/A"),
            "teacher_id": booking_dict.get("teacher_id"),
            "student_count": len(students),
            "students": students,
            "offer_label": booking_dict.get("offer_label", "N/A"),
            "is_exclusive": booking_dict.get("is_exclusive", False),
            "is_approved": booking_dict.get("is_approved", True),
            "notes": (booking_dict.get("notes") or "").strip() or None,
        }

        if booking_dict.get("is_approved"):
            if key not in bookings_by_date_period:
                bookings_by_date_period[key] = []
            bookings_by_date_period[key].append(booking_info)

            # Speichere exklusive genehmigte Buchungen separat
            if booking_dict.get("is_exclusive"):
                exclusive_by_date_period[key] = booking_info
        else:
            # Speichere ausstehende Buchungen oder allgemeine Anfragen (noch nicht genehmigt)
            pending_exclusive_by_date_period[key] = booking_info

    week_overview = []
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr"]

    for i, wd in enumerate(weekdays):
        day_date = monday + timedelta(days=i)
        day_date_str = day_date.strftime("%Y-%m-%d")

        day_schedule = []
        for period in period_keys:
            info = get_period_info(wd, period, fixed_offers=fixed_offers)
            key = f"{day_date_str}_{period}"
            period_bookings = bookings_by_date_period.get(key, [])
            blocked_slot = blocked_by_date_period.get(key)
            exclusive_booking = exclusive_by_date_period.get(key)

            total_students = sum(b["student_count"] for b in period_bookings)
            pending_exclusive = pending_exclusive_by_date_period.get(key)

            # Bei exklusiver Buchung ist der Slot voll belegt
            if exclusive_booking:
                available = 0
            else:
                available = max_students - total_students

            # Prüfe, ob Termin in der Vergangenheit liegt
            is_past = is_past_date(day_date, period)

            # Prüfe, ob es ein Wochenende ist
            is_weekend = day_date.weekday() in [5, 6]

            # Prüfe, ob Buchung für diesen Slot möglich ist
            can_book, _ = check_booking_time(day_date, period)
            can_book = (
                can_book
                and available > 0
                and not blocked_slot
                and not is_past
                and not is_weekend
                and not exclusive_booking
            )

            pt = period_times.get(period, {})
            day_schedule.append(
                {
                    "period": period,
                    "period_label": format_period_label(period),
                    "time": f"{pt.get('start', '?')} - {pt.get('end', '?')}",
                    "type": info["type"],
                    "label": info["label"],
                    "bookings": period_bookings,
                    "total_students": total_students,
                    "available": available,
                    "can_book": can_book,
                    "blocked": blocked_slot,
                    "blocked_reason": blocked_slot.get("reason", "Beratung")
                    if blocked_slot
                    else None,
                    "blocked_icon": blocked_slot.get("icon", "🔧")
                    if blocked_slot
                    else None,
                    "is_past": is_past,
                    "is_weekend": is_weekend,
                    "is_exclusive": exclusive_booking is not None,
                    "exclusive_booking": exclusive_booking,
                    "pending_exclusive": pending_exclusive,
                }
            )
        # Prüfe ob heute
        today = datetime.now(get_berlin_tz()).date()
        is_today = day_date == today

        week_overview.append(
            {
                "weekday": wd,
                "name": weekday_names[i],
                "date": day_date_str,
                "date_formatted": day_date.strftime("%d.%m."),
                "schedule": day_schedule,
                "is_today": is_today,
            }
        )

    # Hole anstehende blockierte Slots für den Liveticker (ab heute, ohne Ferien)
    from models import BlockedSlot, User

    today_str = datetime.now(get_berlin_tz()).strftime("%Y-%m-%d")
    upcoming_query = (
        db.session.query(BlockedSlot, User.username)
        .outerjoin(User, BlockedSlot.blocked_by == User.id)
        .filter(BlockedSlot.date >= today_str)
        .order_by(BlockedSlot.date, BlockedSlot.period)
        .limit(80)
        .all()
    )

    upcoming_blocked = []
    for blocked, username in upcoming_query:
        if is_holiday_blocked_reason(blocked.reason):
            continue
        try:
            date_obj = datetime.strptime(blocked.date, "%Y-%m-%d")
            wd_de = {
                "Mon": "Mo",
                "Tue": "Di",
                "Wed": "Mi",
                "Thu": "Do",
                "Fri": "Fr",
                "Sat": "Sa",
                "Sun": "So",
            }.get(blocked.weekday, blocked.weekday)
            date_formatted = f"{wd_de} {date_obj.strftime('%d.%m.')}"
        except:
            date_formatted = blocked.date

        upcoming_blocked.append(
            {
                "id": blocked.id,
                "date": blocked.date,
                "date_formatted": date_formatted,
                "period": blocked.period,
                "period_label": format_period_label(blocked.period),
                "reason": blocked.reason,
                "icon": blocked.icon or "🔧",
                "blocked_by_id": blocked.blocked_by,
                "blocked_by_name": username or "System",
            }
        )
        if len(upcoming_blocked) >= 15:
            break

    # Hole eigene anstehende Buchungen & ausstehende Exklusiv-Anfragen
    from models import Booking

    user_id = session.get("user_id")
    user_role = session.get("user_role")

    upcoming_bookings = []
    pending_approvals = []

    if user_id:
        # Eigene Buchungen ab heute
        my_bookings_query = (
            Booking.query.filter(
                Booking.teacher_id == user_id, Booking.date >= today_str, Booking.status != 'no_show'
            )
            .order_by(Booking.date, Booking.period)
            .limit(5)
            .all()
        )

        if is_demo_mode():
            from datetime import date as py_date
            today_dt = py_date.today()
            monday = today_dt - timedelta(days=today_dt.weekday())
            start_date = monday.strftime('%Y-%m-%d')
            end_date = (monday + timedelta(days=11)).strftime('%Y-%m-%d')
            demo_bookings = get_demo_bookings_for_week(start_date, end_date)

            class DemoBookingWrapper:
                def __init__(self, d):
                    self.id = d['id']
                    self.date = d['date']
                    self.weekday = d['weekday']
                    self.period = d['period']
                    self.offer_label = d['offer_label']
                    self.is_exclusive = d.get('is_exclusive', False)
                    self.is_approved = d.get('is_approved', True)
                    self.students_json = d['students_json']

            demo_wrapped = [DemoBookingWrapper(b) for b in demo_bookings if b['teacher_id'] == user_id and b['date'] >= today_str]
            my_bookings_query = list(my_bookings_query) + demo_wrapped


        for booking in my_bookings_query:
            try:
                date_obj = datetime.strptime(booking.date, "%Y-%m-%d")
                wd_de = {
                    "Mon": "Mo",
                    "Tue": "Di",
                    "Wed": "Mi",
                    "Thu": "Do",
                    "Fri": "Fr",
                    "Sat": "Sa",
                    "Sun": "So",
                }.get(booking.weekday, booking.weekday)
                date_formatted = f"{wd_de} {date_obj.strftime('%d.%m.')}"
            except:
                date_formatted = booking.date

            is_class_booking = False
            try:
                students = json.loads(booking.students_json)
                if students and all(not s.get("name") for s in students):
                    students_str = f"Ganze Klasse {students[0].get('klasse')}"
                    is_class_booking = True
                else:
                    students_str = ", ".join(
                        [f"{abbreviate_name_filter(s.get('name'))} ({s.get('klasse')})" for s in students]
                    )
            except:
                students_str = ""

            upcoming_bookings.append(
                {
                    "id": booking.id,
                    "date": booking.date,
                    "date_formatted": date_formatted,
                    "period": booking.period,
                    "period_label": format_period_label(booking.period),
                    "offer_label": booking.offer_label,
                    "is_exclusive": booking.is_exclusive,
                    "is_approved": booking.is_approved,
                    "students_str": students_str,
                    "is_class_booking": is_class_booking,
                    "notes": (getattr(booking, "notes", None) or "").strip() or None,
                }
            )

        # Admin-Ausstehende exklusive Anfragen ab heute
        if user_role == "admin":
            pending_query = (
                Booking.query.filter(
                    Booking.is_exclusive == True,
                    Booking.is_approved == False,
                    Booking.date >= today_str,
                )
                .order_by(Booking.date, Booking.period)
                .all()
            )

            for p_booking in pending_query:
                try:
                    date_obj = datetime.strptime(p_booking.date, "%Y-%m-%d")
                    wd_de = {
                        "Mon": "Mo",
                        "Tue": "Di",
                        "Wed": "Mi",
                        "Thu": "Do",
                        "Fri": "Fr",
                        "Sat": "Sa",
                        "Sun": "So",
                    }.get(p_booking.weekday, p_booking.weekday)
                    date_formatted = f"{wd_de} {date_obj.strftime('%d.%m.')}"
                except:
                    date_formatted = p_booking.date

                try:
                    students = json.loads(p_booking.students_json)
                    if students and all(not s.get("name") for s in students):
                        students_str = f"Ganze Klasse {students[0].get('klasse')}"
                    else:
                        students_str = ", ".join(
                            [f"{abbreviate_name_filter(s.get('name'))} ({s.get('klasse')})" for s in students]
                        )
                except:
                    students_str = ""

                pending_approvals.append(
                    {
                        "id": p_booking.id,
                        "date": p_booking.date,
                        "date_formatted": date_formatted,
                        "period": p_booking.period,
                        "teacher_name": p_booking.teacher_name,
                        "students_str": students_str,
                        "offer_label": p_booking.offer_label,
                        "notes": (p_booking.notes or "").strip() or None,
                    }
                )

    # Generiere Wochenliste für den Kalenderwochen-Schnellwähler
    week_selector = []
    real_today = datetime.now(get_berlin_tz()).date()
    real_monday = real_today - timedelta(days=real_today.weekday())

    for w in range(8):
        loop_monday = real_monday + timedelta(weeks=w)
        loop_friday = loop_monday + timedelta(days=4)
        loop_kw = loop_monday.isocalendar()[1]

        label = f"KW {loop_kw:02d} ({loop_monday.strftime('%d.%m.')} – {loop_friday.strftime('%d.%m.')})"
        date_str = loop_monday.strftime("%Y-%m-%d")
        is_selected = loop_monday.strftime("%Y-%m-%d") == monday.strftime("%Y-%m-%d")

        week_selector.append(
            {"label": label, "date": date_str, "is_selected": is_selected}
        )

    from system_config import get_config as _gc

    _dashboard_title = _gc("dashboard_title", "").strip()
    _help_content = _gc("help_content", "").strip()
    _contact_name = _gc("contact_name", "").strip()
    _contact_email = _gc("contact_email", "").strip()
    _contact_phone = _gc("contact_phone", "").strip()
    _contact_text = _gc("contact_text", "").strip()

    # Compute occupancy stats from week_overview
    total_slots = 0
    slots_with_bookings = 0
    blocked_slots = 0
    total_booked_students = 0
    day_stats = []  # Per-day breakdown
    _max_students = get_max_students()

    for day_data in week_overview:
        day_booked = 0
        day_total = 0
        day_blocked = 0
        day_students = 0
        for slot in day_data['schedule']:
            if slot.get('is_weekend'):
                continue
            total_slots += 1
            if slot.get('blocked'):
                blocked_slots += 1
                day_blocked += 1
                continue
            day_total += 1
            if slot.get('bookings'):
                slots_with_bookings += 1
                day_booked += 1
            day_students += slot.get('total_students', 0)
            total_booked_students += slot.get('total_students', 0)
        day_stats.append({
            'name': day_data['name'],
            'date': day_data['date'],
            'date_formatted': day_data['date_formatted'],
            'total_slots': day_total,
            'booked_slots': day_booked,
            'blocked_slots': day_blocked,
            'students': day_students,
        })

    active_slots = total_slots - blocked_slots
    slot_occupancy_pct = round((slots_with_bookings / active_slots * 100) if active_slots > 0 else 0)
    student_capacity = active_slots * _max_students
    student_occupancy_pct = round((total_booked_students / student_capacity * 100) if student_capacity > 0 else 0)

    # Find peak day
    peak_day = max(day_stats, key=lambda d: d['students']) if day_stats else None

    occupancy_stats = {
        'total_slots': total_slots,
        'active_slots': active_slots,
        'slots_with_bookings': slots_with_bookings,
        'blocked_slots': blocked_slots,
        'total_booked_students': total_booked_students,
        'student_capacity': student_capacity,
        'slot_occupancy_pct': slot_occupancy_pct,
        'student_occupancy_pct': student_occupancy_pct,
        'peak_day': peak_day,
        'day_stats': day_stats,
        'max_students_per_slot': _max_students,
    }

    return render_template(
        "dashboard.html",
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
        prev_week_date=prev_week_monday.strftime("%Y-%m-%d"),
        next_week_date=next_week_monday.strftime("%Y-%m-%d"),
        monday_date=monday.strftime("%d.%m.%Y"),
        friday_date=friday.strftime("%d.%m.%Y"),
        max_students=max_students,
        dashboard_title=_dashboard_title,
        help_content=_help_content,
        contact_name=_contact_name,
        contact_email=_contact_email,
        contact_phone=_contact_phone,
        contact_text=_contact_text,
        occupancy_stats=occupancy_stats,
        monday_str=monday.strftime('%Y-%m-%d'),
        current_room=current_room,
        all_rooms=all_rooms,
    )


# Route: Kalenderansicht (Monats-/Jahresübersicht)
@app.route("/calendar")
@app.route("/calendar/<int:year>/<int:month>")
@login_required
def calendar_view(year=None, month=None):
    """Monats-/Jahreskalenderansicht mit Buchungsübersicht"""
    import calendar

    from models import get_blocked_slots_for_week, get_bookings_for_week

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
        1: "Januar",
        2: "Februar",
        3: "März",
        4: "April",
        5: "Mai",
        6: "Juni",
        7: "Juli",
        8: "August",
        9: "September",
        10: "Oktober",
        11: "November",
        12: "Dezember",
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
    from models import BlockedSlot, Booking

    month_bookings = Booking.query.filter(
        Booking.date >= first_day.strftime("%Y-%m-%d"),
        Booking.date <= last_day.strftime("%Y-%m-%d"),
        Booking.status != 'no_show',
    ).all()

    if is_demo_mode():
        from demo_mode import get_demo_bookings_for_week
        demo_bookings = get_demo_bookings_for_week(
            first_day.strftime("%Y-%m-%d"),
            last_day.strftime("%Y-%m-%d")
        )
        class DemoBookingObj:
            def __init__(self, d):
                self.date = d['date']
                self.students_json = d['students_json']
        month_bookings = list(month_bookings) + [DemoBookingObj(d) for d in demo_bookings]

    month_blocked = BlockedSlot.query.filter(
        BlockedSlot.date >= first_day.strftime("%Y-%m-%d"),
        BlockedSlot.date <= last_day.strftime("%Y-%m-%d"),
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
            blocked_reasons[day_key] = blocked.reason or "Blockiert"
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
                day_str = day_date.strftime("%Y-%m-%d")
                is_weekend = day_date.weekday() in [5, 6]
                is_today = day_date == today
                is_past = day_date < today

                booking_count = bookings_per_day.get(day_str, 0)
                blocked_count = blocked_per_day.get(day_str, 0)
                blocked_reason = blocked_reasons.get(day_str, "")

                # Status ermitteln
                if is_weekend:
                    status = "weekend"
                elif blocked_count >= 6:  # Alle 6 Stunden blockiert
                    status = "blocked"
                elif blocked_count > 0:
                    status = "partial_blocked"
                elif booking_count >= 30:  # 6 Stunden * 5 Plätze = 30
                    status = "full"
                elif booking_count > 0:
                    status = "has_bookings"
                else:
                    status = "free"

                week_data.append(
                    {
                        "day": day_num,
                        "date": day_str,
                        "is_weekend": is_weekend,
                        "is_today": is_today,
                        "is_past": is_past,
                        "booking_count": booking_count,
                        "blocked_count": blocked_count,
                        "blocked_reason": blocked_reason,
                        "status": status,
                    }
                )
        weeks.append(week_data)

    # Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        month_name=month_names_de[month],
        weeks=weeks,
        today=today,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        user_role=session.get("user_role"),
    )


# Route: Buchungsseite
@app.route("/book/<date_str>/<int:period>", methods=["GET", "POST"])
@login_required
def book(date_str, period):
    """Seite zum Erstellen einer neuen Buchung"""

    # Im Demo-Modus sind keine echten Buchungen möglich
    if is_demo_mode():
        flash("Im Demo-Modus können keine Buchungen erstellt werden.", "error")
        return redirect(url_for("dashboard"))

    # Request-Modus prüfen
    request_mode = request.args.get("request_mode") == "1" or request.form.get("request_mode") == "1"

    # Hole gewählten Raum
    from models import get_room_by_id, get_default_room
    room_id = request.args.get("room", type=int) or request.form.get("room", type=int)
    current_room = None
    if room_id:
        current_room = get_room_by_id(room_id)
    if not current_room:
        current_room = get_default_room()
    room_id = current_room.id if current_room else 1

    # Hole den Benutzernamen aus der Session für das Formular
    user_display_name = session.get("user_username", "")
    # Falls E-Mail als Username verwendet wird, extrahiere den Namen
    if "@" in user_display_name:
        user_display_name = user_display_name.split("@")[0].replace(".", " ").title()

    # Validiere Datum und Stunde
    try:
        booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        flash("Ungültiges Datum.", "error")
        return redirect(url_for("dashboard", room=room_id))

    period_times = get_period_times()
    if period not in period_times:
        flash("Ungültiges Zeitfenster.", "error")
        return redirect(url_for("dashboard", room=room_id))

    # Prüfe, ob Termin in der Vergangenheit liegt
    if is_past_date(booking_date, period):
        flash(
            "Dieser Termin liegt in der Vergangenheit und kann nicht gebucht werden.",
            "error",
        )
        return redirect(url_for("dashboard", room=room_id))

    # Prüfe, ob es ein Wochenende ist (Samstag=5, Sonntag=6)
    if booking_date.weekday() in [5, 6]:
        flash("Buchungen sind am Wochenende nicht möglich.", "error")
        return redirect(url_for("dashboard", room=room_id))

    # Ermittle Wochentag und Stundeninfo
    weekday = booking_date.strftime("%a")
    period_info = get_period_info(weekday, period)

    # Prüfe verfügbare Plätze
    current_students = count_students_for_period(date_str, period, room_id=room_id)
    available_spots = get_max_students() - current_students

    if not request_mode and available_spots <= 0:
        flash("Diese Stunde ist bereits voll belegt.", "error")
        return redirect(url_for("dashboard", date=date_str, room=room_id))

    # Prüfe, ob Slot für Beratung blockiert ist (nur Admins können blockierte Slots sehen)
    from models import get_blocked_slot, is_slot_blocked

    if is_slot_blocked(date_str, period, room_id=room_id):
        blocked_info = get_blocked_slot(date_str, period, room_id=room_id)
        reason = blocked_info.get("reason", "Beratung") if blocked_info else "Beratung"
        flash(
            f"Dieser Slot ist für {reason} blockiert und kann nicht gebucht werden.",
            "error",
        )
        return redirect(url_for("dashboard", date=date_str, room=room_id))

    # Prüfe, ob bereits eine genehmigte exklusive Buchung existiert
    from models import Booking

    exclusive_booking = Booking.query.filter_by(
        date=date_str, period=period, is_exclusive=True, is_approved=True, room_id=room_id
    ).filter(Booking.status != 'no_show').first()
    if not request_mode and exclusive_booking:
        flash(
            "Dieser Slot ist für ein Einzelangebot reserviert und kann nicht gebucht werden.",
            "error",
        )
        return redirect(url_for("dashboard", date=date_str, room=room_id))

    # Prüfe Zeitfenster
    can_book, time_message = check_booking_time(booking_date, period)
    if not request_mode and not can_book:
        flash(time_message or "Buchung nicht möglich.", "error")
        return redirect(url_for("dashboard", date=date_str, room=room_id))

    if request.method == "POST":
        # Hole Lehrkraft-Informationen
        teacher_name = request.form.get("teacher_name", "").strip() or user_display_name
        teacher_class = request.form.get("teacher_class", "").strip()

        if request_mode:
            notes = request.form.get("notes", "").strip()
            if not notes:
                flash("Bitte geben Sie eine Nachricht/Begründung ein.", "error")
                return render_template(
                    "book.html",
                    date_str=date_str,
                    period=period,
                    period_info=period_info,
                    period_time=_get_period_dict(period),
                    available_spots=available_spots,
                    free_modules=get_free_courses(),
                    user_name=user_display_name,
                    user_email="",
                    school_classes=get_school_classes_list(),
                    max_students=get_max_students(),
                    request_mode=request_mode,
                )
            
            # Erstelle Anfrage in Datenbank (is_request = True)
            booking_id = create_booking(
                date=date_str,
                weekday=weekday,
                period=period,
                teacher_id=session["user_id"],
                students=[],
                offer_type=period_info["type"],
                offer_label=period_info["label"] if period_info["type"] == "fest" else "Freie Wahl",
                teacher_name=teacher_name,
                teacher_class="",
                notes=notes,
                is_exclusive=False,
                is_approved=False,
                room_id=room_id,
                is_request=True,
            )
            if booking_id:
                # Create notification for admin
                notification_message = f"✉️ ANFRAGE: {teacher_name} möchte für {period_info['label'] if period_info['type'] == 'fest' else 'Freie Wahl'} am {date_str} (Stunde {period}) buchen: {notes}"
                create_notification(
                    booking_id=booking_id,
                    message=notification_message,
                    notification_type="booking_request",
                    recipient_role="admin",
                )
                flash("Anfrage erfolgreich gesendet. ✉️", "success")
                return redirect(url_for("meine_buchungen"))
            else:
                flash("Fehler beim Senden der Anfrage.", "error")
                return redirect(url_for("dashboard", date=date_str, room=room_id))

        if not teacher_name or not teacher_class:
            flash("Bitte geben Sie Ihren Namen und Ihre Klasse ein.", "error")
            return render_template(
                "book.html",
                date_str=date_str,
                period=period,
                period_info=period_info,
                period_time=_get_period_dict(period),
                available_spots=available_spots,
                free_modules=get_free_courses(),
                user_name=user_display_name,
                user_email="",
                school_classes=get_school_classes_list(),
                max_students=get_max_students(),
                request_mode=request_mode,
            )

        # Hole Anzahl der Schüler
        num_students = int(request.form.get("num_students", 1))

        _max_s = get_max_students()
        if num_students < 1 or num_students > _max_s:
            flash(f"Bitte wählen Sie zwischen 1 und {_max_s} Schülern.", "error")
            return render_template(
                "book.html",
                date_str=date_str,
                period=period,
                period_info=period_info,
                period_time=_get_period_dict(period),
                available_spots=available_spots,
                free_modules=get_free_courses(),
                user_name=user_display_name,
                user_email="",
                school_classes=get_school_classes_list(),
                max_students=_max_s,
                request_mode=request_mode,
            )

        # Prüfe erneut verfügbare Plätze
        if not request_mode and num_students > available_spots:
            flash(
                f"Nicht genug Plätze verfügbar. Nur noch {available_spots} Plätze frei.",
                "error",
            )
            return redirect(url_for("dashboard", date=date_str, room=room_id))

        # Sammle Schülerdaten und prüfe Doppelbuchungen
        whole_class = request.form.get("whole_class") == "1"
        names_optional = request.form.get("names_optional") == "1" or whole_class
        students = []

        def _book_render(**extra):
            return render_template(
                "book.html",
                date_str=date_str,
                period=period,
                period_info=period_info,
                period_time=_get_period_dict(period),
                available_spots=available_spots,
                free_modules=get_free_courses(),
                user_name=user_display_name,
                user_email=display_user_email if "display_user_email" in dir() else "",
                school_classes=get_school_classes_list(),
                max_students=get_max_students(),
                room=current_room,
                request_mode=request_mode,
                **extra,
            )

        if whole_class:
            # Ganze Klasse buchen: Slot wird vollständig belegt
            _max = get_max_students()
            if not request_mode and _max > available_spots:
                flash(
                    f"Klassenbuchung nicht möglich – nur noch {available_spots} Plätze frei. Bitte einzelne Schüler*innen eintragen.",
                    "error",
                )
                return redirect(url_for("dashboard", date=date_str, room=room_id))
            num_students = _max
            for _ in range(num_students):
                students.append({"name": "", "klasse": teacher_class})
        else:
            for i in range(num_students):
                name = request.form.get(f"student_name_{i}", "").strip()
                klasse = request.form.get(f"student_class_{i}", "").strip()

                if not klasse:
                    flash(
                        "Bitte wählen Sie für alle Schüler*innen eine Klasse aus.",
                        "error",
                    )
                    return _book_render()
                if not names_optional and not name:
                    flash("Bitte geben Sie alle Schüler-Namen ein.", "error")
                    return _book_render()

                if name:
                    double_booking = check_student_double_booking(
                        name, klasse, date_str, period
                    )
                    if double_booking["is_booked"]:
                        flash(
                            f"⚠️ Doppelbuchung verhindert: {double_booking['booking_info']}",
                            "error",
                        )
                        return _book_render()

                students.append({"name": name, "klasse": klasse})

        # Hole Modul-Wahl (nur bei freien Stunden)
        if period_info["type"] == "frei":
            selected_module = request.form.get("module", "")
            if selected_module not in get_free_courses():
                flash("Bitte wählen Sie ein Modul.", "error")
                return render_template(
                    "book.html",
                    date_str=date_str,
                    period=period,
                    period_info=period_info,
                    period_time=_get_period_dict(period),
                    available_spots=available_spots,
                    free_modules=get_free_courses(),
                    user_name=user_display_name,
                    school_classes=get_school_classes_list(),
                    request_mode=request_mode,
                )
            offer_label = selected_module
        else:
            offer_label = period_info["label"]

        # Hole optionale Notizen
        notes = request.form.get("notes", "").strip()

        # Prüfe ob exklusive Buchung (nur 1 Schüler)
        is_exclusive = request.form.get("is_exclusive") == "1" and len(students) == 1

        # Erstelle Buchung in Datenbank
        booking_id = create_booking(
            date=date_str,
            weekday=weekday,
            period=period,
            teacher_id=session["user_id"],
            students=students,
            offer_type=period_info["type"],
            offer_label=offer_label,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            notes=notes if notes else None,
            is_exclusive=is_exclusive,
            is_approved=False if request_mode else (not is_exclusive),
            room_id=room_id,
            is_request=request_mode,
        )

        if booking_id:
            # Sende E-Mail-Benachrichtigung
            booking_data = {
                "date": date_str,
                "weekday": weekday,
                "period": period,
                "students": students,
                "offer_type": period_info["type"],
                "offer_label": offer_label,
                "teacher_name": teacher_name,
                "teacher_class": teacher_class,
                "students_json": json.dumps(students, ensure_ascii=False),
                "is_exclusive": is_exclusive,
                "is_approved": False if request_mode else (not is_exclusive),
            }

            # Erstelle Notification in der Datenbank
            if request_mode:
                notification_message = f"✉️ ANFRAGE: {teacher_name} möchte für {offer_label} am {date_str} (Stunde {period}) buchen: {notes}"
                notification_type = "booking_request"
            elif is_exclusive:
                notification_message = f"🔒 EXKLUSIVE Buchung (Freigabe nötig): {teacher_name} möchte 1 Schüler exklusiv für {offer_label} am {date_str} (Stunde {period}) anmelden."
                notification_type = "exclusive_booking_pending"
            else:
                notification_message = f"Neue Buchung: {teacher_name} hat {len(students)} Schüler für {offer_label} am {date_str} (Stunde {period}) angemeldet."
                notification_type = "new_booking"

            notification_id = create_notification(
                booking_id=booking_id,
                message=notification_message,
                notification_type=notification_type,
                recipient_role="admin",
                metadata={
                    "teacher_name": teacher_name,
                    "teacher_class": teacher_class,
                    "date": date_str,
                    "period": period,
                    "offer_label": offer_label,
                    "students_count": len(students),
                    "is_exclusive": is_exclusive,
                    "is_request": request_mode,
                },
            )

            # Sende E-Mails im Hintergrund (verhindert Timeout bei Buchung)
            send_email_confirmation = request.form.get("send_email_confirmation") == "1"
            user_id = session.get("user_id")
            user_email = ""
            if user_id:
                user_data = get_user_by_id(user_id)
                if user_data:
                    user_email = user_data.get("email", "")

            def _send_emails_background(bd, send_confirm, u_email, exclusive, is_req):
                # Admin-Benachrichtigung
                try:
                    send_booking_notification(bd)
                except Exception as e:
                    print(f"[EMAIL] Admin-Benachrichtigung fehlgeschlagen: {e}")
                # Lehrer-Bestätigung
                if send_confirm and u_email:
                    try:
                        if is_req:
                            # Send request pending email
                            from email_service import send_exclusive_pending_email
                            send_exclusive_pending_email(u_email, bd)
                        elif exclusive:
                            from email_service import send_exclusive_pending_email

                            send_exclusive_pending_email(u_email, bd)
                        else:
                            from email_service import send_user_booking_confirmation

                            send_user_booking_confirmation(u_email, bd)
                    except Exception as e:
                        print(f"[EMAIL] Lehrer-Bestätigung fehlgeschlagen: {e}")

            start_background_task(
                _send_emails_background,
                booking_data,
                send_email_confirmation,
                user_email,
                is_exclusive,
                request_mode,
            )

            # Broadcast an SSE-Clients
            if notification_id:
                unread_count = get_unread_notification_count(recipient_role="admin")
                broadcast_notification(
                    {
                        "type": "new_booking",
                        "notification_id": notification_id,
                        "message": notification_message,
                        "booking_data": {
                            "date": date_str,
                            "period": period,
                            "teacher_name": teacher_name,
                            "offer_label": offer_label,
                            "students_count": len(students),
                        },
                        "unread_count": unread_count,
                    }
                )

            if request_mode:
                flash(
                    "Buchungsanfrage erfolgreich gesendet! Der Administrator wurde benachrichtigt.",
                    "info",
                )
            elif is_exclusive:
                flash(
                    f"Exklusive Buchung eingereicht! Die Buchung wartet auf Freigabe durch den Admin. Sie werden per E-Mail benachrichtigt.",
                    "info",
                )
            elif whole_class:
                flash(
                    f"Klassenbuchung erfolgreich! Klasse {teacher_class} für {offer_label} eingetragen. Der Slot ist vollständig belegt.",
                    "success",
                )
            else:
                flash(
                    f"Buchung erfolgreich! {len(students)} Schüler für {offer_label} angemeldet.",
                    "success",
                )
            return redirect(url_for("dashboard", date=date_str, room=room_id))
        else:
            flash("Fehler beim Erstellen der Buchung.", "error")

    # Hole E-Mail aus der Datenbank für die Anzeige
    display_user_email = ""
    user_id = session.get("user_id")
    if user_id:
        user_data = get_user_by_id(user_id)
        if user_data:
            display_user_email = user_data.get("email", "")

    return render_template(
        "book.html",
        date_str=date_str,
        period=period,
        period_info=period_info,
        period_time=_get_period_dict(period),
        available_spots=available_spots,
        free_modules=get_free_courses(),
        user_name=user_display_name,
        user_email=display_user_email,
        school_classes=get_school_classes_list(),
        max_students=get_max_students(),
        room=current_room,
        request_mode=request_mode,
    )


# Hilfsfunktion: Prüft ob eine Buchung noch bearbeitet/gelöscht werden kann
def can_modify_booking(booking_date_str, period):
    """
    Prüft ob eine Buchung noch bearbeitet/gelöscht werden kann.
    Änderungen sind bis 1 Stunde vor dem Termin möglich.

    Returns:
        Tuple (can_modify: bool, reason: str or None)
    """
    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        now = datetime.now(get_berlin_tz())
        today = now.date()

        # Vergangenes Datum?
        if booking_date < today:
            return False, "Vergangener Termin"

        # Heute: Prüfe ob weniger als 1 Stunde bis zum Termin
        if booking_date == today:
            period_start_str = _get_period_dict(period)["start"]
            period_start_time = datetime.strptime(period_start_str, "%H:%M").time()
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
@app.route("/meine-buchungen")
@login_required
def meine_buchungen():
    """Zeigt alle Buchungen des Benutzers (oder alle für Admin)"""
    from models import Booking, get_all_bookings

    user_id = session["user_id"]
    is_admin = session.get("user_role") == "admin"

    # Admin sieht alle Buchungen, normale Benutzer nur ihre eigenen
    if is_admin:
        all_bookings = get_all_bookings()
    else:
        bookings_query = (
            Booking.query.filter_by(teacher_id=user_id)
            .filter(Booking.is_request == False)
            .order_by(Booking.date.desc(), Booking.period)
            .all()
        )
        all_bookings = [b.to_dict() for b in bookings_query]

    # Im Demo-Modus: Fake-Buchungen hinzufügen
    if is_demo_mode():
        from datetime import date
        from demo_mode import get_demo_bookings_for_week
        today_date = date.today()
        monday = today_date - timedelta(days=today_date.weekday())
        start_date = monday.strftime('%Y-%m-%d')
        end_date = (monday + timedelta(days=11)).strftime('%Y-%m-%d')
        demo_bookings = get_demo_bookings_for_week(start_date, end_date)
        if not is_admin:
            demo_bookings = [b for b in demo_bookings if b['teacher_id'] == user_id]
        all_bookings = list(all_bookings) + demo_bookings


    # Deutsche Wochentagsnamen
    weekday_names_de = {
        "Mon": "Montag",
        "Tue": "Dienstag",
        "Wed": "Mittwoch",
        "Thu": "Donnerstag",
        "Fri": "Freitag",
        "Sat": "Samstag",
        "Sun": "Sonntag",
    }

    bookings_display = []
    for booking in all_bookings:
        booking_dict = dict(booking)
        students = (
            json.loads(booking_dict["students_json"])
            if booking_dict.get("students_json")
            else []
        )

        # Prüfe ob Buchung bearbeitet/gelöscht werden kann
        can_modify, modify_reason = can_modify_booking(
            booking_dict["date"], booking_dict["period"]
        )

        # Admin kann immer bearbeiten
        if is_admin:
            can_modify = True
            modify_reason = None

        # Datum formatieren
        try:
            booking_date = datetime.strptime(booking_dict["date"], "%Y-%m-%d").date()
            date_formatted = booking_date.strftime("%d.%m.%Y")
            is_past = booking_date < datetime.now(get_berlin_tz()).date()
        except:
            date_formatted = booking_dict["date"]
            is_past = False

        # Created_at formatieren
        created_at = booking_dict.get("created_at", "")
        if created_at:
            try:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                else:
                    created_dt = created_at
                created_at_formatted = created_dt.strftime("%d.%m.%Y %H:%M")
            except:
                created_at_formatted = str(created_at)
        else:
            created_at_formatted = "-"

        bookings_display.append(
            {
                "id": booking_dict["id"],
                "date": booking_dict["date"],
                "date_formatted": date_formatted,
                "weekday": booking_dict["weekday"],
                "weekday_name": weekday_names_de.get(
                    booking_dict["weekday"], booking_dict["weekday"]
                ),
                "period": booking_dict["period"],
                "period_label": format_period_label(booking_dict["period"]),
                "period_time": f"{_get_period_dict(booking_dict['period'])['start']} - {_get_period_dict(booking_dict['period'])['end']}",
                "teacher_name": booking_dict.get("teacher_name", "N/A"),
                "teacher_class": booking_dict.get("teacher_class", "N/A"),
                "offer_label": booking_dict["offer_label"],
                "offer_type": booking_dict["offer_type"],
                "students": students,
                "can_modify": can_modify,
                "modify_reason": modify_reason,
                "is_past": is_past,
                "created_at_formatted": created_at_formatted,
                "notes": (booking_dict.get("notes") or "").strip() or None,
                "is_exclusive": booking_dict.get("is_exclusive", False),
                "is_approved": booking_dict.get("is_approved", True),
                "status": booking_dict.get("status", "booked"),
                "admin_reply": (booking_dict.get("admin_reply") or "").strip() or None,
            }
        )

    return render_template(
        "meine_buchungen.html", bookings=bookings_display, is_admin=is_admin
    )


# Route: Posteingang
@app.route("/posteingang")
@login_required
def posteingang():
    """Zeigt alle Benachrichtigungen im persönlichen Posteingang"""
    from models import get_recent_notifications, Booking

    user_id = session["user_id"]
    is_admin = session.get("user_role") == "admin"

    if is_admin:
        notifications = get_recent_notifications(recipient_role="admin", limit=50)
        inquiries = (
            Booking.query.filter_by(is_request=True)
            .order_by(Booking.date.desc(), Booking.period)
            .all()
        )
    else:
        notifications = get_recent_notifications(recipient_user_id=user_id, limit=50)
        inquiries = (
            Booking.query.filter_by(teacher_id=user_id, is_request=True)
            .order_by(Booking.date.desc(), Booking.period)
            .all()
        )

    # Convert to dict for uniform rendering
    inquiries_data = [b.to_dict() for b in inquiries]

    return render_template(
        "posteingang.html",
        notifications=notifications,
        inquiries=inquiries_data,
        is_admin=is_admin
    )


# Route: Eigene Buchung bearbeiten
@app.route("/meine-buchungen/bearbeiten/<int:booking_id>", methods=["GET", "POST"])
@login_required
def edit_my_booking(booking_id):
    """Benutzer kann eigene Buchung bearbeiten (bis 1 Stunde vorher)"""
    from models import Booking, get_booking_by_id, update_booking

    user_id = session["user_id"]
    is_admin = session.get("user_role") == "admin"

    booking_row = get_booking_by_id(booking_id)
    if not booking_row:
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("meine_buchungen"))

    booking = dict(booking_row)

    # Prüfe Berechtigung: Eigene Buchung oder Admin
    if booking["teacher_id"] != user_id and not is_admin:
        flash("Sie können nur Ihre eigenen Buchungen bearbeiten.", "error")
        return redirect(url_for("meine_buchungen"))

    # Prüfe ob Bearbeitung noch möglich ist (außer Admin)
    if not is_admin:
        can_modify, modify_reason = can_modify_booking(
            booking["date"], booking["period"]
        )
        if not can_modify:
            flash(
                f"Diese Buchung kann nicht mehr bearbeitet werden: {modify_reason}",
                "error",
            )
            return redirect(url_for("meine_buchungen"))

    # Deutsche Wochentagsnamen
    weekday_names_de = {
        "Mon": "Montag",
        "Tue": "Dienstag",
        "Wed": "Mittwoch",
        "Thu": "Donnerstag",
        "Fri": "Freitag",
        "Sat": "Samstag",
        "Sun": "Sonntag",
    }

    students = (
        json.loads(booking["students_json"]) if booking.get("students_json") else []
    )

    # Berechne verfügbare Plätze (ohne die aktuelle Buchung)
    current_students = count_students_for_period(booking["date"], booking["period"])
    available_spots = get_max_students() - (current_students - len(students))

    # Datum formatieren
    try:
        booking_date = datetime.strptime(booking["date"], "%Y-%m-%d").date()
        date_formatted = booking_date.strftime("%d.%m.%Y")
    except:
        date_formatted = booking["date"]

    if request.method == "POST":
        # CSRF-Token Validierung
        csrf_token = request.form.get("csrf_token", "")
        if not validate_csrf_token(csrf_token):
            flash(
                "Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error"
            )
            return redirect(url_for("edit_my_booking", booking_id=booking_id))

        try:
            num_students = int(request.form.get("num_students", 1))
        except (ValueError, TypeError):
            flash("Ungültige Schüleranzahl.", "error")
            return redirect(url_for("edit_my_booking", booking_id=booking_id))

        if num_students < 1 or num_students > available_spots:
            flash(
                f"Bitte wählen Sie zwischen 1 und {available_spots} Schüler*innen.",
                "error",
            )
            return redirect(url_for("edit_my_booking", booking_id=booking_id))

        # Sammle Schülerdaten
        names_optional_edit2 = request.form.get("names_optional") == "1"
        new_students = []
        for i in range(num_students):
            name = request.form.get(f"student_name_{i}", "").strip()
            klasse = request.form.get(f"student_class_{i}", "").strip()

            if not klasse:
                flash(
                    "Bitte wählen Sie für alle Schüler*innen eine Klasse aus.", "error"
                )
                return redirect(url_for("edit_my_booking", booking_id=booking_id))
            if not names_optional_edit2 and not name:
                flash(
                    'Bitte geben Sie alle Schüler-Namen ein oder aktivieren Sie „Klasse als Gruppe buchen".',
                    "error",
                )
                return redirect(url_for("edit_my_booking", booking_id=booking_id))

            # Doppelbuchungs-Check nur wenn Name angegeben
            if name:
                double_booking = check_student_double_booking(
                    name,
                    klasse,
                    booking["date"],
                    booking["period"],
                    exclude_booking_id=booking_id,
                )
                if double_booking["is_booked"]:
                    flash(
                        f"⚠️ Doppelbuchung verhindert: {double_booking['booking_info']}",
                        "error",
                    )
                    return redirect(url_for("edit_my_booking", booking_id=booking_id))

            new_students.append({"name": name, "klasse": klasse})

        # Hole Modul-Wahl (nur bei freien Stunden)
        if booking["offer_type"] == "frei":
            selected_module = request.form.get("module", "")
            if selected_module not in get_free_courses():
                flash("Bitte wählen Sie ein Modul.", "error")
                return redirect(url_for("edit_my_booking", booking_id=booking_id))
            offer_label = selected_module
        else:
            offer_label = booking["offer_label"]

        # Aktualisiere Buchung (Notizen bleiben unverändert bei Lehrer-Bearbeitung)
        if update_booking(
            booking_id=booking_id,
            date=booking["date"],
            weekday=booking["weekday"],
            period=booking["period"],
            teacher_id=booking["teacher_id"],
            students=new_students,
            offer_type=booking["offer_type"],
            offer_label=offer_label,
            teacher_name=booking.get("teacher_name"),
            teacher_class=booking.get("teacher_class"),
            notes=booking.get("notes"),
        ):
            flash("Buchung erfolgreich aktualisiert!", "success")
            return redirect(url_for("meine_buchungen"))
        else:
            flash("Fehler beim Aktualisieren der Buchung.", "error")

    # Booking-Objekt für Template vorbereiten
    booking_display = {
        "id": booking["id"],
        "date": booking["date"],
        "date_formatted": date_formatted,
        "weekday": booking["weekday"],
        "weekday_name": weekday_names_de.get(booking["weekday"], booking["weekday"]),
        "period": booking["period"],
        "offer_label": booking["offer_label"],
        "offer_type": booking["offer_type"],
        "students": students,
    }

    return render_template(
        "edit_my_booking.html",
        booking=booking_display,
        period_times=get_period_times(),
        free_modules=get_free_courses(),
        school_classes=get_school_classes_list(),
        max_students=available_spots,
        available_spots=available_spots - len(students),
    )


# Route: Eigene Buchung löschen
@app.route("/meine-buchungen/loeschen/<int:booking_id>", methods=["POST"])
@login_required
def delete_my_booking(booking_id):
    """Benutzer kann eigene Buchung löschen (bis 1 Stunde vorher)"""
    from models import delete_booking, get_booking_by_id

    # CSRF-Token Validierung
    csrf_token = request.form.get("csrf_token", "")
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept") == "application/json"
    )

    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Ungültiges Sicherheits-Token."}
            ), 400
        flash("Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error")
        return redirect(url_for("meine_buchungen"))

    user_id = session["user_id"]
    is_admin = session.get("user_role") == "admin"

    booking_row = get_booking_by_id(booking_id)
    if not booking_row:
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Buchung nicht gefunden."}
            ), 404
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("meine_buchungen"))

    booking = dict(booking_row)

    # Prüfe Berechtigung: Eigene Buchung oder Admin
    if booking["teacher_id"] != user_id and not is_admin:
        if is_ajax:
            return jsonify(
                {
                    "success": False,
                    "message": "Sie können nur Ihre eigenen Buchungen löschen.",
                }
            ), 403
        flash("Sie können nur Ihre eigenen Buchungen löschen.", "error")
        return redirect(url_for("meine_buchungen"))

    # Prüfe ob Löschen noch möglich ist (außer Admin)
    if not is_admin:
        can_modify, modify_reason = can_modify_booking(
            booking["date"], booking["period"]
        )
        if not can_modify:
            if is_ajax:
                return jsonify(
                    {
                        "success": False,
                        "message": f"Diese Buchung kann nicht mehr gelöscht werden: {modify_reason}",
                    }
                ), 400
            flash(
                f"Diese Buchung kann nicht mehr gelöscht werden: {modify_reason}",
                "error",
            )
            return redirect(url_for("meine_buchungen"))

    # Lösche Buchung
    if delete_booking(booking_id):
        if is_ajax:
            return jsonify(
                {"success": True, "message": "Buchung erfolgreich gelöscht."}
            )
        flash("Buchung erfolgreich gelöscht.", "success")
    else:
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Buchung konnte nicht gelöscht werden."}
            ), 500
        flash("Buchung konnte nicht gelöscht werden.", "error")

    return redirect(url_for("meine_buchungen"))


@app.route("/meine-buchungen/toggle-no-show/<int:booking_id>", methods=["POST"])
@login_required
def toggle_booking_no_show(booking_id):
    """Schaltet den No-Show-Status einer Buchung um (booked / no_show)"""
    from models import Booking

    # CSRF-Token Validierung
    csrf_token = request.form.get("csrf_token", "")
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept") == "application/json"
    )

    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify({"success": False, "message": "Ungültiges Sicherheits-Token."}), 400
        flash("Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error")
        return redirect(url_for("meine_buchungen"))

    user_id = session["user_id"]
    is_admin = session.get("user_role") == "admin"

    booking = Booking.query.get(booking_id)
    if not booking:
        if is_ajax:
            return jsonify({"success": False, "message": "Buchung nicht gefunden."}), 404
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("meine_buchungen"))

    # Prüfe Berechtigung: Eigene Buchung oder Admin
    if booking.teacher_id != user_id and not is_admin:
        if is_ajax:
            return jsonify({"success": False, "message": "Sie können nur Ihre eigenen Buchungen ändern."}), 403
        flash("Sie können nur Ihre eigenen Buchungen ändern.", "error")
        return redirect(url_for("meine_buchungen"))

    # Toggle status
    if booking.status == "no_show":
        booking.status = "booked"
        message = "Buchungs-Status erfolgreich auf 'gebucht' zurückgesetzt."
    else:
        booking.status = "no_show"
        message = "Buchung wurde als No-Show markiert. Kapazität wurde freigegeben."

    try:
        db.session.commit()
        if is_ajax:
            return jsonify({"success": True, "message": message, "status": booking.status})
        flash(message, "success")
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Umschalten des No-Show-Status: {e}")
        if is_ajax:
            return jsonify({"success": False, "message": "Fehler beim Aktualisieren der Datenbank."}), 500
        flash("Fehler beim Aktualisieren des Buchungsstatus.", "error")

    return redirect(url_for("meine_buchungen"))


# Route: Admin-Bereich
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    """Admin-Seite für Benutzerverwaltung und Buchungsübersicht"""

    if request.method == "POST":
        # Neue Lehrkraft anlegen
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()

        if not username or not password:
            flash("Bitte füllen Sie alle Felder aus.", "error")
        else:
            user_id = create_user(
                username, password, "teacher", email if email else None
            )
            if user_id:
                flash(f"Lehrkraft {username} erfolgreich angelegt.", "success")
            else:
                flash("Benutzername existiert bereits.", "error")

    # Hole alle Benutzer
    users = get_all_users()

    # Hole ausstehende exklusive Buchungen
    from models import get_pending_exclusive_bookings

    pending_exclusive = get_pending_exclusive_bookings()
    pending_exclusive_display = []
    for booking in pending_exclusive:
        booking_dict = dict(booking)
        students = (
            json.loads(booking_dict["students_json"])
            if booking_dict.get("students_json")
            else []
        )
        pending_exclusive_display.append(
            {
                "id": booking_dict["id"],
                "date": booking_dict["date"],
                "weekday": booking_dict["weekday"],
                "period": booking_dict["period"],
                "teacher_email": booking_dict.get("teacher_email"),
                "teacher_name": booking_dict.get("teacher_name", "N/A"),
                "teacher_class": booking_dict.get("teacher_class", "N/A"),
                "offer_label": booking_dict["offer_label"],
                "offer_type": booking_dict["offer_type"],
                "students": students,
                "student_count": len(students),
                "notes": booking_dict.get("notes"),
            }
        )

    # Hole alle Buchungen
    filter_date = request.args.get("filter_date", "")
    if filter_date:
        bookings = get_bookings_by_date(filter_date)
    else:
        bookings = get_all_bookings()

    if is_demo_mode():
        from demo_mode import get_demo_bookings_for_week, get_demo_bookings_for_date
        if filter_date:
            demo_bookings = get_demo_bookings_for_date(filter_date)
        else:
            from datetime import date as py_date
            today_dt = py_date.today()
            monday = today_dt - timedelta(days=today_dt.weekday())
            start_date = monday.strftime('%Y-%m-%d')
            end_date = (monday + timedelta(days=11)).strftime('%Y-%m-%d')
            demo_bookings = get_demo_bookings_for_week(start_date, end_date)
        bookings = list(bookings) + demo_bookings


    # Konvertiere Buchungen für Anzeige
    bookings_display = []
    for booking in bookings:
        booking_dict = dict(booking)
        students = (
            json.loads(booking_dict["students_json"])
            if booking_dict.get("students_json")
            else []
        )
        bookings_display.append(
            {
                "id": booking_dict["id"],
                "date": booking_dict["date"],
                "weekday": booking_dict["weekday"],
                "period": booking_dict["period"],
                "teacher_email": booking_dict.get("teacher_email", ""),
                "teacher_name": booking_dict.get("teacher_name", "N/A"),
                "teacher_class": booking_dict.get("teacher_class", "N/A"),
                "offer_label": booking_dict["offer_label"],
                "offer_type": booking_dict["offer_type"],
                "students": students,
                "student_count": len(students),
                "notes": booking_dict.get("notes"),
                "is_exclusive": booking_dict.get("is_exclusive", False),
                "is_approved": booking_dict.get("is_approved", True),
            }
        )

    return render_template(
        "admin.html",
        users=users,
        bookings=bookings_display,
        pending_exclusive=pending_exclusive_display,
        filter_date=filter_date,
    )


# Route: Exklusive Buchung genehmigen
@app.route("/admin/approve_exclusive/<int:booking_id>", methods=["POST"])
@admin_required
def approve_exclusive(booking_id):
    """Genehmigt eine Buchungsanfrage/exklusive Buchung"""
    from database import db
    from models import Booking, get_booking_by_id, create_notification

    csrf_token = request.form.get("csrf_token", "")
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept") == "application/json"
    )

    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Ungültiges Sicherheits-Token."}
            ), 400
        flash("Ungültiges Sicherheits-Token.", "error")
        return redirect(url_for("admin"))

    # Hole optionales Feedback aus dem Formular
    admin_reply = request.form.get("admin_reply", "").strip() or request.form.get("reply", "").strip()

    booking = Booking.query.get(booking_id)
    if not booking:
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Buchung nicht gefunden."}
            ), 404
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("admin"))

    date_str = booking.date
    period = booking.period
    teacher_email = booking.teacher.email if booking.teacher else None
    teacher_name = booking.teacher_name or "Lehrkraft"
    students = json.loads(booking.students_json) if booking.students_json else []
    student_name = students[0]["name"] if students else "Schüler/in"

    removed_count = 0
    affected_teachers = []

    # Falls exklusiv, lösche konfliktierende Buchungen
    if booking.is_exclusive:
        conflicting_bookings = Booking.query.filter(
            Booking.date == date_str, Booking.period == period, Booking.id != booking_id, Booking.status != 'no_show'
        ).all()

        for conflict in conflicting_bookings:
            conflict_students = (
                json.loads(conflict.students_json) if conflict.students_json else []
            )
            affected_teachers.append(
                {
                    "email": conflict.teacher_email,
                    "name": conflict.teacher_name or "Lehrkraft",
                    "booking_info": {
                        "date": conflict.date,
                        "period": conflict.period,
                        "offer_label": conflict.offer_label,
                        "students": conflict_students,
                    },
                }
            )

        for conflict in conflicting_bookings:
            db.session.delete(conflict)
            removed_count += 1

    # Genehmige die Buchung und speichere die admin_reply
    if booking.is_request:
        reply_text = admin_reply if admin_reply else "Ja, geht in Ordnung. Du kannst die Kinder schicken."
        booking.admin_reply = reply_text
        booking.is_approved = True
        db.session.commit()

        # System-Benachrichtigung für die Lehrkraft erzeugen (Reine Anfrage / Nachricht)
        create_notification(
            booking_id=booking.id,
            message=f"💬 Freigabe für Deine Anfrage: {booking.offer_label} am {booking.date} ({booking.period}. Stunde). Antwort: {reply_text} (Du kannst die Kinder schicken)",
            notification_type="request_approved",
            recipient_role="teacher",
            recipient_user_id=booking.teacher_id,
            metadata={
                "date": booking.date,
                "period": booking.period,
                "offer_label": booking.offer_label,
                "admin_reply": reply_text,
            }
        )
    else:
        booking.is_approved = True
        if admin_reply:
            booking.admin_reply = admin_reply
        db.session.commit()

        # System-Benachrichtigung für die Lehrkraft erzeugen
        create_notification(
            booking_id=booking.id,
            message=f"✅ Deine Buchung für {booking.offer_label} am {booking.date} ({booking.period}. Stunde) wurde genehmigt.{' Antwort: ' + admin_reply if admin_reply else ''}",
            notification_type="booking_approved",
            recipient_role="teacher",
            recipient_user_id=booking.teacher_id,
            metadata={
                "date": booking.date,
                "period": booking.period,
                "offer_label": booking.offer_label,
                "admin_reply": admin_reply,
            }
        )

    # Sende E-Mails im Hintergrund
    def _send_approval_emails(t_email, t_name, s_name, d_str, per, affected, is_req=False, reply_txt=""):
        if t_email:
            try:
                if is_req:
                    from email_service import send_email
                    from email_service import _get_app_name
                    app_name = _get_app_name()
                    subject = f"Antwort auf Deine Anfrage – {app_name}"
                    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
                    <body style="margin:0;padding:20px;background:#f3f4f6;">
                        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
                            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                                <h2 style="color:white;margin:0;font-size:20px;">Antwort auf Deine Anfrage</h2>
                            </div>
                            <div style="padding:30px;">
                                <div style="background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                                    <strong>Hallo {t_name}!</strong>
                                    <p style="margin:10px 0 0 0;">Deine Anfrage für den {d_str} ({per}. Stunde) wurde freigegeben.</p>
                                </div>
                                <div style="background:#f8fafc;border-radius:10px;padding:20px;margin-bottom:20px;">
                                    <p style="margin:0;color:#6b7280;font-size:0.9rem;"><strong>Nachricht des Administrators:</strong></p>
                                    <p style="margin:10px 0 0 0;font-size:1.1rem;color:#1f2937;font-style:italic;">"{reply_txt}"</p>
                                    <p style="margin:15px 0 0 0;font-weight:600;color:#166534;">Du kannst die Kinder schicken. 🚸</p>
                                </div>
                                <div style="margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#6b7280;font-size:12px;">
                                    Diese Anfrage ist keine feste Buchung im Kalender, sondern eine freigegebene Absprache.
                                </div>
                            </div>
                        </div>
                    </body></html>"""
                    text = f"Hallo {t_name},\n\nDeine Anfrage für den {d_str} ({per}. Stunde) wurde freigegeben.\nAntwort des Admins: {reply_txt}\nDu kannst die Kinder schicken."
                    send_email(t_email, subject, html, text)
                else:
                    from email_service import send_exclusive_approved_email
                    send_exclusive_approved_email(
                        teacher_email=t_email,
                        teacher_name=t_name,
                        student_name=s_name,
                        date_str=d_str,
                        period=per,
                    )
            except Exception as e:
                print(f"[EMAIL] Genehmigungs-E-Mail fehlgeschlagen: {e}")
        from email_service import send_booking_removed_due_to_exclusive

        for affected_teacher in affected:
            if affected_teacher["email"]:
                try:
                    send_booking_removed_due_to_exclusive(
                        teacher_email=affected_teacher["email"],
                        teacher_name=affected_teacher["name"],
                        booking_info=affected_teacher["booking_info"],
                        exclusive_info={"teacher": t_name, "student": s_name},
                    )
                except Exception as e:
                    print(f"[EMAIL] Stornierungs-E-Mail fehlgeschlagen: {e}")

    start_background_task(
        _send_approval_emails,
        teacher_email,
        teacher_name,
        student_name,
        date_str,
        period,
        affected_teachers,
        booking.is_request,
        booking.admin_reply
    )

    if is_ajax:
        return jsonify({"success": True, "message": "Anfrage erfolgreich genehmigt."})

    if removed_count > 0:
        flash(
            f"Anfrage genehmigt. {removed_count} andere Buchung(en) wurden storniert und die Lehrkräfte benachrichtigt.",
            "success",
        )
    else:
        flash(
            "Anfrage wurde erfolgreich genehmigt.",
            "success",
        )
    return redirect(url_for("admin"))


# Route: Exklusive Buchung ablehnen
@app.route("/admin/reject_exclusive/<int:booking_id>", methods=["POST"])
@admin_required
def reject_exclusive(booking_id):
    """Lehnt eine Buchung/Anfrage ab"""
    from database import db
    from models import Booking, create_notification

    csrf_token = request.form.get("csrf_token", "")
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept") == "application/json"
    )

    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Ungültiges Sicherheits-Token."}
            ), 400
        flash("Ungültiges Sicherheits-Token.", "error")
        return redirect(url_for("admin"))

    # Hole Ablehnungsgrund aus dem Formular
    rejection_reason = request.form.get("reason", "").strip()

    booking = Booking.query.get(booking_id)
    if not booking:
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Buchung nicht gefunden."}
            ), 404
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("admin"))

    teacher_email = booking.teacher.email if booking.teacher else None
    teacher_name = booking.teacher_name or "Lehrkraft"
    students = json.loads(booking.students_json) if booking.students_json else []
    student_name = students[0]["name"] if students else "Schüler/in"
    date_str = booking.date
    period = booking.period

    try:
        # Status auf 'rejected' setzen statt löschen
        booking.status = "rejected"
        booking.is_approved = False
        booking.admin_reply = rejection_reason
        db.session.commit()

        # System-Benachrichtigung für die Lehrkraft erzeugen
        create_notification(
            booking_id=booking.id,
            message=f"❌ Deine Buchung für {booking.offer_label} am {booking.date} ({booking.period}. Stunde) wurde abgelehnt.{' Begründung: ' + rejection_reason if rejection_reason else ''}",
            notification_type="booking_rejected",
            recipient_role="teacher",
            recipient_user_id=booking.teacher_id,
            metadata={
                "date": booking.date,
                "period": booking.period,
                "offer_label": booking.offer_label,
                "rejection_reason": rejection_reason,
            }
        )

        # Sende Ablehnungs-E-Mail im Hintergrund
        if teacher_email:
            def _send_rejection(t_email, t_name, s_name, d_str, per, reason):
                try:
                    from email_service import send_exclusive_rejected_email

                    send_exclusive_rejected_email(
                        teacher_email=t_email,
                        teacher_name=t_name,
                        student_name=s_name,
                        date_str=d_str,
                        period=per,
                        rejection_reason=reason,
                    )
                except Exception as e:
                    print(f"[EMAIL] Ablehnungs-E-Mail fehlgeschlagen: {e}")

            start_background_task(
                _send_rejection,
                teacher_email,
                teacher_name,
                student_name,
                date_str,
                period,
                rejection_reason,
            )

        if is_ajax:
            return jsonify(
                {"success": True, "message": "Anfrage erfolgreich abgelehnt und Nachricht gespeichert."}
            )
        flash(
            "Anfrage wurde abgelehnt und Nachricht gespeichert. Die Lehrkraft wurde benachrichtigt.",
            "success",
        )
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Ablehnen der Buchung: {e}")
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Fehler beim Ablehnen der Buchung."}
            ), 500
        flash("Fehler beim Ablehnen der Buchung.", "error")

    return redirect(url_for("admin"))


# Route: Buchung erstellen (nur Admin)
@app.route("/admin/create_booking", methods=["GET", "POST"])
@admin_required
def admin_create_booking():
    """Admin kann Buchungen für beliebige Lehrkräfte erstellen"""
    from models import get_booking_by_id

    if request.method == "POST":
        date_str = request.form.get("date", "").strip()

        try:
            period = int(request.form.get("period", 1))
            teacher_id = int(request.form.get("teacher_id", 0))
            num_students = int(request.form.get("num_students", 1))
        except (ValueError, TypeError):
            flash(
                "Ungültige Eingabe für Stunde, Lehrkraft oder Schüleranzahl.", "error"
            )
            users = get_all_users()
            return render_template(
                "admin_edit_booking.html",
                booking=None,
                users=users,
                free_modules=get_free_courses(),
                period_times=get_period_times(),
            )

        teacher_name = request.form.get("teacher_name", "").strip()
        teacher_class = request.form.get("teacher_class", "").strip()

        if (
            not date_str
            or not teacher_id
            or not teacher_name
            or not teacher_class
            or num_students < 1
            or num_students > get_max_students()
        ):
            flash(
                f"Bitte füllen Sie alle Pflichtfelder aus und wählen Sie 1-{get_max_students()} Schüler.",
                "error",
            )
            users = get_all_users()
            return render_template(
                "admin_edit_booking.html",
                booking=None,
                users=users,
                free_modules=get_free_courses(),
                period_times=get_period_times(),
            )

        try:
            booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            flash("Ungültiges Datum.", "error")
            users = get_all_users()
            return render_template(
                "admin_edit_booking.html",
                booking=None,
                users=users,
                free_modules=get_free_courses(),
                period_times=get_period_times(),
            )

        weekday = booking_date.strftime("%a")
        period_info = get_period_info(weekday, period)

        # Prüfe Kapazität vor dem Erstellen der Buchung
        room_id = request.form.get("room_id", type=int)
        if not room_id:
            from models import get_default_room
            def_room = get_default_room()
            room_id = def_room.id if def_room else 1

        current_students = count_students_for_period(date_str, period, room_id=room_id)
        available_spots = get_max_students() - current_students

        if num_students > available_spots:
            flash(
                f"Nicht genug Plätze verfügbar. Nur noch {available_spots} Plätze frei.",
                "error",
            )
            users = get_all_users()
            rooms = get_all_rooms(active_only=True)
            return render_template(
                "admin_edit_booking.html",
                booking=None,
                users=users,
                rooms=rooms,
                free_modules=get_free_courses(),
                period_times=get_period_times(),
            )

        students = []
        names_optional_admin = request.form.get("names_optional") == "1"
        for i in range(num_students):
            name = request.form.get(f"student_name_{i}", "").strip()
            klasse = request.form.get(f"student_class_{i}", "").strip()

            if not klasse:
                flash(
                    "Bitte wählen Sie für alle Schüler*innen eine Klasse aus.", "error"
                )
                users = get_all_users()
                rooms = get_all_rooms(active_only=True)
                return render_template(
                    "admin_edit_booking.html",
                    booking=None,
                    users=users,
                    rooms=rooms,
                    free_modules=get_free_courses(),
                    period_times=get_period_times(),
                )
            if not names_optional_admin and not name:
                flash(
                    'Bitte geben Sie alle Schüler-Namen ein oder aktivieren Sie „Namen optional".',
                    "error",
                )
                users = get_all_users()
                rooms = get_all_rooms(active_only=True)
                return render_template(
                    "admin_edit_booking.html",
                    booking=None,
                    users=users,
                    rooms=rooms,
                    free_modules=get_free_courses(),
                    period_times=get_period_times(),
                )

            students.append({"name": name, "klasse": klasse})

        if period_info["type"] == "frei":
            selected_module = request.form.get("module", "")
            if selected_module not in get_free_courses():
                flash("Bitte wählen Sie ein Modul.", "error")
                users = get_all_users()
                rooms = get_all_rooms(active_only=True)
                return render_template(
                    "admin_edit_booking.html",
                    booking=None,
                    users=users,
                    rooms=rooms,
                    free_modules=get_free_courses(),
                    period_times=get_period_times(),
                )
            offer_label = selected_module
        else:
            offer_label = period_info["label"]

        # Hole optionale Notizen (Admin-Buchungen)
        notes = request.form.get("notes", "").strip()

        booking_id = create_booking(
            date=date_str,
            weekday=weekday,
            period=period,
            teacher_id=teacher_id,
            students=students,
            offer_type=period_info["type"],
            offer_label=offer_label,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            notes=notes if notes else None,
            room_id=room_id,
        )

        if booking_id:
            flash(
                f"Buchung erfolgreich erstellt! {len(students)} Schüler für {offer_label} angemeldet.",
                "success",
            )
            return redirect(url_for("admin"))
        else:
            flash("Fehler beim Erstellen der Buchung.", "error")

    users = get_all_users()
    rooms = get_all_rooms(active_only=True)
    return render_template(
        "admin_edit_booking.html",
        booking=None,
        users=users,
        rooms=rooms,
        free_modules=get_free_courses(),
        period_times=get_period_times(),
    )


# Route: Buchung bearbeiten (nur Admin)
@app.route("/admin/edit_booking/<int:booking_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_booking(booking_id):
    """Admin kann bestehende Buchungen bearbeiten"""
    from models import get_booking_by_id, update_booking

    booking_row = get_booking_by_id(booking_id)
    if not booking_row:
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("admin"))

    booking = dict(booking_row)
    users = get_all_users()
    rooms = get_all_rooms(active_only=True)

    def _render_edit(booking_data, **extra):
        return render_template(
            "admin_edit_booking.html",
            booking=booking_data,
            users=users,
            rooms=rooms,
            free_modules=get_free_courses(),
            period_times=get_period_times(),
            **extra,
        )

    if request.method == "POST":
        date_str = request.form.get("date", "").strip()
        room_id = request.form.get("room_id", type=int) or booking.get("room_id")

        try:
            period = int(request.form.get("period", 1))
            teacher_id = int(request.form.get("teacher_id", 0))
            num_students = int(request.form.get("num_students", 1))
        except (ValueError, TypeError):
            flash(
                "Ungültige Eingabe für Stunde, Lehrkraft oder Schüleranzahl.", "error"
            )
            students = (
                json.loads(booking["students_json"])
                if booking.get("students_json")
                else []
            )
            booking_display = dict(booking)
            booking_display["students"] = students
            return _render_edit(booking_display)

        teacher_name = request.form.get("teacher_name", "").strip()
        teacher_class = request.form.get("teacher_class", "").strip()

        if (
            not date_str
            or not teacher_id
            or not teacher_name
            or not teacher_class
            or num_students < 1
            or num_students > get_max_students()
        ):
            flash(
                f"Bitte füllen Sie alle Pflichtfelder aus und wählen Sie 1-{get_max_students()} Schüler.",
                "error",
            )
            students = (
                json.loads(booking["students_json"])
                if booking.get("students_json")
                else []
            )
            booking_display = dict(booking)
            booking_display["students"] = students
            return _render_edit(booking_display)

        try:
            booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            flash("Ungültiges Datum.", "error")
            students = (
                json.loads(booking["students_json"])
                if booking.get("students_json")
                else []
            )
            booking_display = dict(booking)
            booking_display["students"] = students
            return _render_edit(booking_display)

        weekday = booking_date.strftime("%a")
        period_info = get_period_info(weekday, period)

        # Prüfe Kapazität: Berechne verfügbare Plätze ohne die aktuelle Buchung
        current_students = count_students_for_period(date_str, period, room_id=room_id)
        old_booking_students = len(
            json.loads(booking["students_json"]) if booking.get("students_json") else []
        )
        available_spots = get_max_students() - (current_students - old_booking_students)

        if num_students > available_spots:
            flash(
                f"Nicht genug Plätze verfügbar. Nur noch {available_spots} Plätze frei.",
                "error",
            )
            students = (
                json.loads(booking["students_json"])
                if booking.get("students_json")
                else []
            )
            booking_display = dict(booking)
            booking_display["students"] = students
            return _render_edit(booking_display)

        students = []
        names_optional_edit = request.form.get("names_optional") == "1"
        for i in range(num_students):
            name = request.form.get(f"student_name_{i}", "").strip()
            klasse = request.form.get(f"student_class_{i}", "").strip()

            if not klasse:
                flash(
                    "Bitte wählen Sie für alle Schüler*innen eine Klasse aus.", "error"
                )
                _old_students = (
                    json.loads(booking["students_json"])
                    if booking.get("students_json")
                    else []
                )
                booking_display = dict(booking)
                booking_display["students"] = _old_students
                return _render_edit(booking_display)
            if not names_optional_edit and not name:
                flash(
                    'Bitte geben Sie alle Schüler-Namen ein oder aktivieren Sie „Namen optional".',
                    "error",
                )
                _old_students = (
                    json.loads(booking["students_json"])
                    if booking.get("students_json")
                    else []
                )
                booking_display = dict(booking)
                booking_display["students"] = _old_students
                return _render_edit(booking_display)

            students.append({"name": name, "klasse": klasse})

        if period_info["type"] == "frei":
            selected_module = request.form.get("module", "")
            if selected_module not in get_free_courses():
                flash("Bitte wählen Sie ein Modul.", "error")
                students = (
                    json.loads(booking["students_json"])
                    if booking.get("students_json")
                    else []
                )
                booking_display = dict(booking)
                booking_display["students"] = students
                return _render_edit(booking_display)
            offer_label = selected_module
        else:
            offer_label = period_info["label"]

        # Hole optionale Notizen (Admin kann Notizen bearbeiten)
        notes = request.form.get("notes", "").strip()

        if update_booking(
            booking_id=booking_id,
            date=date_str,
            weekday=weekday,
            period=period,
            teacher_id=teacher_id,
            students=students,
            offer_type=period_info["type"],
            offer_label=offer_label,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            notes=notes if notes else None,
            room_id=room_id,
        ):
            flash(f"Buchung erfolgreich aktualisiert!", "success")
            return redirect(url_for("admin"))
        else:
            flash("Fehler beim Aktualisieren der Buchung.", "error")

    students = (
        json.loads(booking["students_json"]) if booking.get("students_json") else []
    )
    booking_display = dict(booking)
    booking_display["students"] = students

    return _render_edit(booking_display)


# Route: Buchung löschen (nur Admin)
@app.route("/admin/delete_booking/<int:booking_id>", methods=["POST"])
@admin_required
def delete_booking_route(booking_id):
    """Löscht eine Buchung"""
    from models import delete_booking

    # Lösche Buchung
    if delete_booking(booking_id):
        flash("Buchung erfolgreich gelöscht.", "success")
    else:
        flash("Buchung konnte nicht gelöscht werden.", "error")

    return redirect(url_for("admin"))


# Route: Slots verwalten (nur Admin)
@app.route("/admin/manage_slots", methods=["GET", "POST"])
@admin_required
def manage_slots():
    """Admin kann feste Slot-Namen umbenennen"""
    from models import update_slot_name

    if request.method == "POST":
        weekday = request.form.get("weekday")
        period_str = request.form.get("period")
        period = int(period_str) if period_str else 0
        label = request.form.get("label", "").strip()

        if weekday and period and label:
            if update_slot_name(weekday, period, label):
                flash(f"Slot-Name erfolgreich aktualisiert!", "success")
            else:
                flash("Fehler beim Aktualisieren des Slot-Namens.", "error")
        else:
            flash("Bitte füllen Sie alle Felder aus.", "error")

        return redirect(url_for("manage_slots"))

    fixed_slots = []
    weekdays = {
        "Mon": "Montag",
        "Tue": "Dienstag",
        "Wed": "Mittwoch",
        "Thu": "Donnerstag",
        "Fri": "Freitag",
    }

    for weekday_code, weekday_name in weekdays.items():
        if weekday_code in get_fixed_offers():
            for period, default_label in (
                get_fixed_offers().get(weekday_code, {}).items()
            ):
                period_info = get_period_info(weekday_code, period)
                fixed_slots.append(
                    {
                        "weekday_code": weekday_code,
                        "weekday_name": weekday_name,
                        "period": period,
                        "period_time": f"{_get_period_dict(period)['start']} - {_get_period_dict(period)['end']}",
                        "default_label": default_label,
                        "current_label": period_info["label"],
                    }
                )

    return render_template("admin_manage_slots.html", fixed_slots=fixed_slots)


@app.route("/admin/block_slot", methods=["POST"])
@admin_required
def admin_block_slot():
    """Admin blockiert einen Slot für Beratungsgespräche"""
    from models import block_slot, is_slot_blocked

    # CSRF-Token Validierung
    csrf_token = request.form.get("csrf_token", "")
    if not validate_csrf_token(csrf_token):
        flash("Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    date_str = request.form.get("date", "").strip()
    period = request.form.get("period", type=int)
    reason = request.form.get("reason", "Beratung").strip()
    icon = request.form.get("icon", "🔧").strip()
    room_id = request.form.get("room_id", type=int)

    # Validiere Grund-Länge
    if reason and len(reason) > 200:
        reason = reason[:200]

    # Validiere Icon
    allowed_icons = [
        "🔧",
        "💬",
        "📚",
        "🏖️",
        "🎉",
        "🎓",
        "🤒",
        "🤝",
        "💻",
        "📞",
        "🚪",
        "⚠️",
    ]
    if icon not in allowed_icons:
        icon = "🔧"

    if not date_str or not period:
        flash("Ungültige Slot-Daten.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    try:
        booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        weekday = booking_date.strftime("%a")
    except:
        flash("Ungültiges Datum.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    if not room_id:
        from models import get_default_room
        def_room = get_default_room()
        room_id = def_room.id if def_room else 1

    if is_slot_blocked(date_str, period, room_id=room_id):
        flash("Dieser Slot ist bereits blockiert.", "warning")
    else:
        admin_id = session.get("user_id")
        if block_slot(date_str, weekday, period, admin_id, reason, icon, room_id=room_id):
            flash(f"Slot erfolgreich für {reason} blockiert.", "success")
        else:
            flash("Fehler beim Blockieren des Slots.", "error")

    return redirect(request.referrer or url_for("dashboard"))


@app.route("/admin/unblock_slot", methods=["POST"])
@admin_required
def admin_unblock_slot():
    """Admin gibt einen blockierten Slot wieder frei"""
    from models import unblock_slot

    # CSRF-Token Validierung
    csrf_token = request.form.get("csrf_token", "")
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept") == "application/json"
    )

    if not validate_csrf_token(csrf_token):
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Ungültiges Sicherheits-Token."}
            ), 400
        flash("Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    date_str = request.form.get("date", "").strip()
    period = request.form.get("period", type=int)
    room_id = request.form.get("room_id", type=int)

    if not date_str or not period:
        if is_ajax:
            return jsonify({"success": False, "message": "Ungültige Slot-Daten."}), 400
        flash("Ungültige Slot-Daten.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    if not room_id:
        from models import get_default_room
        def_room = get_default_room()
        room_id = def_room.id if def_room else 1

    if unblock_slot(date_str, period, room_id=room_id):
        if is_ajax:
            return jsonify(
                {"success": True, "message": "Slot erfolgreich freigegeben."}
            )
        flash("Slot erfolgreich freigegeben.", "success")
    else:
        if is_ajax:
            return jsonify(
                {"success": False, "message": "Fehler beim Freigeben des Slots."}
            ), 500
        flash("Fehler beim Freigeben des Slots.", "error")

    return redirect(request.referrer or url_for("dashboard"))


@app.route("/admin/export_occupancy_report")
@login_required
def export_occupancy_report():
    """Generiert einen CSV-Belegungsbericht für eine Kalenderwoche"""
    import csv
    import io
    from models import get_bookings_for_week, get_blocked_slots_for_week

    # Nur Admins oder Lehrer dürfen exportieren
    if session.get("user_role") not in ["admin", "teacher"]:
        flash("Keine Berechtigung für diese Aktion.", "error")
        return redirect(url_for("dashboard"))

    date_param = request.args.get("date", "")
    room_id = request.args.get("room", type=int)
    
    # Resolve room if room_id is set
    room_name = ""
    if room_id:
        from models import get_room_by_id
        room_obj = get_room_by_id(room_id)
        if room_obj:
            room_name = "_" + room_obj.get("name", "").replace(" ", "_")

    try:
        if date_param:
            ref_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        else:
            ref_date = datetime.now(get_berlin_tz()).date()
    except:
        ref_date = datetime.now(get_berlin_tz()).date()

    monday = ref_date - timedelta(days=ref_date.weekday())
    friday = monday + timedelta(days=4)
    kw = monday.isocalendar()[1]

    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
    max_students = get_max_students()
    period_times = get_period_times()

    # Fetch all bookings for the week
    all_bookings = get_bookings_for_week(monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d"), room_id=room_id)
    blocked = get_blocked_slots_for_week(monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d"), room_id=room_id)

    bookings_map = {}
    for b in all_bookings:
        bd = b if isinstance(b, dict) else b.__dict__
        key = f"{bd.get('date', '')}_{bd.get('period', '')}"
        if key not in bookings_map:
            bookings_map[key] = []
        bookings_map[key].append(bd)

    blocked_set = set()
    for bl in blocked:
        bld = bl if isinstance(bl, dict) else bl.__dict__
        blocked_set.add(f"{bld.get('date', '')}_{bld.get('period', '')}")

    output = io.StringIO()
    # BOM for Excel UTF-8 compatibility
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Datum', 'Wochentag', 'Stunde', 'Kursname', 'Status', 'Gebuchte Schüler', 'Max. Plätze', 'Auslastung %', 'Lehrkräfte', 'Schülerliste'])

    for i, wd in enumerate(weekdays):
        day_date = monday + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")
        day_formatted = day_date.strftime("%d.%m.%Y")

        for period in get_ordered_period_numbers():
            info = get_period_info(wd, period)
            key = f"{day_str}_{period}"
            kurs = info.get('label', 'Freie Wahl') if info.get('type') == 'fest' else 'Freie Wahl'

            if key in blocked_set:
                writer.writerow([day_formatted, weekday_names[i], f'{period}. Stunde', kurs, 'Blockiert', 0, max_students, '0%', '-', '-'])
                continue

            slot_bookings = bookings_map.get(key, [])
            total_students = sum(len(b.get('students', [])) for b in slot_bookings)
            pct = round(total_students / max_students * 100) if max_students > 0 else 0
            teachers = ', '.join(set(b.get('teacher_name', '?') for b in slot_bookings)) or '-'

            student_list = []
            for b in slot_bookings:
                for s in b.get('students', []):
                    name = s.get('name', '')
                    klasse = s.get('klasse', '')
                    if name:
                        student_list.append(f"{name} ({klasse})")
                    elif klasse:
                        student_list.append(f"Klasse {klasse} (ganze Klasse)")
            students_str = ', '.join(student_list) or '-'

            status = 'Belegt' if slot_bookings else 'Frei'
            writer.writerow([day_formatted, weekday_names[i], f'{period}. Stunde', kurs, status, total_students, max_students, f'{pct}%', teachers, students_str])

    output.seek(0)
    filename = f"Belegungsbericht_KW{kw}_{monday.strftime('%Y')}{room_name}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.route("/admin/setup_holidays_2026", methods=["POST"])
@admin_required
def admin_setup_holidays_2026():
    """Legt alle Niedersachsen-Ferien und Feiertage für 2026 automatisch an"""
    from models import bulk_block_slots

    # CSRF-Token Validierung
    csrf_token = request.form.get("csrf_token", "")
    if not validate_csrf_token(csrf_token):
        flash("Ungültiges Sicherheits-Token.", "error")
        return redirect(url_for("admin_bulk_block"))

    admin_id = session.get("user_id")
    total_blocked = 0
    total_skipped = 0

    # Niedersachsen Schulferien 2026
    holidays_2026 = [
        # Winterferien: 02.02. - 03.02.2026
        ("2026-02-02", "2026-02-03", "❄️ Winterferien", "❄️"),
        # Osterferien: 23.03. - 04.04.2026
        ("2026-03-23", "2026-04-04", "🐣 Osterferien", "🐣"),
        # Pfingstferien: 26.05.2026
        ("2026-05-26", "2026-05-26", "🌸 Pfingstferien", "🌸"),
        # Sommerferien: 16.07. - 26.08.2026
        ("2026-07-16", "2026-08-26", "☀️ Sommerferien", "☀️"),
        # Herbstferien: 12.10. - 24.10.2026
        ("2026-10-12", "2026-10-24", "🍂 Herbstferien", "🍂"),
        # Weihnachtsferien: 23.12.2026 - 06.01.2027
        ("2026-12-23", "2027-01-06", "🎄 Weihnachtsferien", "🎄"),
    ]

    # Gesetzliche Feiertage Niedersachsen 2026
    public_holidays_2026 = [
        ("2026-01-01", "2026-01-01", "🎆 Neujahr", "🎆"),
        ("2026-04-03", "2026-04-03", "✝️ Karfreitag", "✝️"),
        ("2026-04-06", "2026-04-06", "✝️ Ostermontag", "✝️"),
        ("2026-05-01", "2026-05-01", "🔧 Tag der Arbeit", "🔧"),
        ("2026-05-14", "2026-05-14", "☁️ Christi Himmelfahrt", "☁️"),
        ("2026-05-25", "2026-05-25", "🕊️ Pfingstmontag", "🕊️"),
        ("2026-10-03", "2026-10-03", "🇩🇪 Tag der Deutschen Einheit", "🇩🇪"),
        ("2026-10-31", "2026-10-31", "⛪ Reformationstag", "⛪"),
        ("2026-12-25", "2026-12-25", "🎄 1. Weihnachtstag", "🎄"),
        ("2026-12-26", "2026-12-26", "🎄 2. Weihnachtstag", "🎄"),
    ]

    all_holidays = holidays_2026 + public_holidays_2026

    for start_date, end_date, reason, icon in all_holidays:
        result = bulk_block_slots(start_date, end_date, admin_id, reason, icon=icon)
        if result["success"]:
            total_blocked += result["blocked_count"]
            total_skipped += result["skipped_count"]

    flash(
        f"✅ Ferien 2026 angelegt: {total_blocked} Slots blockiert, {total_skipped} bereits vorhanden.",
        "success",
    )
    return redirect(url_for("admin_bulk_block"))


@app.route("/admin/bulk_block", methods=["GET", "POST"])
@admin_required
def admin_bulk_block():
    """Admin kann mehrere Slots auf einmal sperren (z.B. für Ferien)"""
    from models import bulk_block_slots, bulk_unblock_slots, get_all_blocked_slots

    blocked_slots = get_all_blocked_slots()

    if request.method == "POST":
        # CSRF-Token Validierung
        csrf_token = request.form.get("csrf_token", "")
        if not validate_csrf_token(csrf_token):
            flash(
                "Ungültiges Sicherheits-Token. Bitte versuchen Sie es erneut.", "error"
            )
            return redirect(url_for("admin_bulk_block"))

        action = request.form.get("action", "block")
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()
        reason = request.form.get("reason", "Ferien").strip()

        # Stunden auswählen (Checkboxen)
        periods = request.form.getlist("periods", type=int)
        if not periods:
            periods = None  # Alle Stunden

        # Validierung
        if not start_date or not end_date:
            flash("Bitte Start- und Enddatum angeben.", "error")
            return redirect(url_for("admin_bulk_block"))

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            if start > end:
                flash("Startdatum muss vor dem Enddatum liegen.", "error")
                return redirect(url_for("admin_bulk_block"))
        except:
            flash("Ungültiges Datumsformat.", "error")
            return redirect(url_for("admin_bulk_block"))

        admin_id = session.get("user_id")
        room_id_form = request.form.get("room_id")
        room_id = int(room_id_form) if room_id_form and room_id_form.strip() else None

        if action == "block":
            result = bulk_block_slots(start_date, end_date, admin_id, reason, periods, room_id=room_id)
            if result["success"]:
                flash(
                    f"✅ {result['blocked_count']} Slots erfolgreich gesperrt ({result['skipped_count']} bereits gesperrt übersprungen).",
                    "success",
                )
            else:
                flash(
                    f"Fehler beim Sperren: {result.get('error', 'Unbekannter Fehler')}",
                    "error",
                )
        elif action == "unblock":
            result = bulk_unblock_slots(start_date, end_date, periods, room_id=room_id)
            if result["success"]:
                flash(
                    f"✅ {result['unblocked_count']} Slots erfolgreich freigegeben.",
                    "success",
                )
            else:
                flash(
                    f"Fehler beim Freigeben: {result.get('error', 'Unbekannter Fehler')}",
                    "error",
                )

        return redirect(url_for("admin_bulk_block"))

    return render_template(
        "admin_bulk_block.html",
        blocked_slots=blocked_slots,
        period_times=get_period_times(),
        rooms=get_all_rooms(active_only=True),
    )


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


@app.route("/api/notifications/recent", methods=["GET"])
@login_required
def api_get_recent_notifications():
    """Holt die neuesten Benachrichtigungen"""
    limit = request.args.get("limit", 10, type=int)
    limit = min(limit, 50)
    is_admin = session.get("user_role") == "admin"

    if is_admin:
        notifications = get_recent_notifications(recipient_role="admin", limit=limit)
    else:
        notifications = get_recent_notifications(recipient_user_id=session["user_id"], limit=limit)
    return jsonify({"success": True, "notifications": notifications})


@app.route("/api/notifications/unread_count", methods=["GET"])
@login_required
def api_get_unread_count():
    """Holt die Anzahl der ungelesenen Benachrichtigungen"""
    is_admin = session.get("user_role") == "admin"
    if is_admin:
        count = get_unread_notification_count(recipient_role="admin")
    else:
        count = get_unread_notification_count(recipient_user_id=session["user_id"])
    return jsonify({"success": True, "count": count})


@app.route("/api/notifications/<int:notification_id>/mark_read", methods=["POST"])
@login_required
def api_mark_notification_read(notification_id):
    """Markiert eine Benachrichtigung als gelesen"""
    csrf_token = request.json.get("csrf_token", "") if request.json else ""
    if not validate_csrf_token(csrf_token):
        return jsonify({"success": False, "error": "Invalid CSRF token"}), 403

    success = mark_notification_as_read(notification_id)
    return jsonify({"success": success})


@app.route("/api/notifications/mark_all_read", methods=["POST"])
@login_required
def api_mark_all_notifications_read():
    """Markiert alle Benachrichtigungen als gelesen"""
    csrf_token = request.json.get("csrf_token", "") if request.json else ""
    if not validate_csrf_token(csrf_token):
        return jsonify({"success": False, "error": "Invalid CSRF token"}), 403

    is_admin = session.get("user_role") == "admin"
    if is_admin:
        success = mark_all_notifications_as_read(recipient_role="admin")
    else:
        success = mark_all_notifications_as_read(recipient_user_id=session["user_id"])
    return jsonify({"success": success})


@app.route("/api/admin/theme", methods=["POST"])
@admin_required
def api_save_admin_theme():
    """Speichert das Seiten-Design dauerhaft in der Datenbank (systemweit)."""
    payload = request.get_json(silent=True) or {}
    csrf_token = payload.get("csrf_token", "")
    if not validate_csrf_token(csrf_token):
        return jsonify({"success": False, "error": "Ungültiges Sicherheitstoken."}), 403

    theme = payload.get("theme", "classic")
    if theme not in ADMIN_THEME_IDS:
        return jsonify({"success": False, "error": "Unbekanntes Design."}), 400

    from system_config import set_config

    if not set_config("admin_theme", theme, category="appearance"):
        return jsonify({"success": False, "error": "Speichern fehlgeschlagen."}), 500

    return jsonify({"success": True, "theme": theme})


# ── Admin CMS: Inhalte bearbeiten ────────────────────────────────────────────


@app.route("/admin/cms")
@admin_required
def admin_cms():
    """CMS-Seite für Admin: Login-Texte, Datenschutz, Impressum, Hinweistexte, Demo-Modus"""
    from system_config import get_config

    cms = {
        "login_title": get_config("login_title", ""),
        "login_subtitle": get_config("login_subtitle", ""),
        "login_notice": get_config("login_notice", ""),
        "privacy_text": get_config("cms_privacy_text", ""),
        "imprint_text": get_config("cms_imprint_text", ""),
        "dashboard_notice": get_config("dashboard_notice", ""),
        "booking_notice": get_config("booking_notice", ""),
        "dashboard_title": get_config("dashboard_title", ""),
        "help_content": get_config("help_content", ""),
        "contact_name": get_config("contact_name", ""),
        "contact_email": get_config("contact_email", ""),
        "contact_phone": get_config("contact_phone", ""),
        "contact_text": get_config("contact_text", ""),
        "logo_filename": get_config("logo_filename", ""),
        "favicon_filename": get_config("favicon_filename", ""),
        "primary_color": get_config("primary_color", "#E91E63"),
        "smtp_host": get_config("smtp_host", ""),
        "smtp_port": get_config("smtp_port", "587"),
        "smtp_user": get_config("smtp_user", ""),
        "smtp_tls": get_config("smtp_tls", "starttls"),
        "smtp_from": get_config("smtp_from", ""),
        "admin_email": get_config("admin_email", ""),
        "email_provider": get_config("email_provider", "smtp"),
        "resend_api_key": get_config("resend_api_key", ""),
        "resend_from": get_config("resend_from", ""),
        "brevo_api_key": get_config("brevo_api_key", ""),
        "brevo_from": get_config("brevo_from", ""),
        "brevo_from_name": get_config("brevo_from_name", "SportOase"),
        "iserv_admin_email": get_config("iserv_admin_email", ""),
        "iserv_domain": get_config("iserv_domain", ""),
        "font_size_base": get_config("font_size_base", "100"),
        "font_size_headings": get_config("font_size_headings", "100"),
        "font_size_table": get_config("font_size_table", "100"),
        "font_size_widgets": get_config("font_size_widgets", "100"),
        "iserv_client_id": get_config("iserv_client_id", ""),
        "font_size_base": get_config("font_size_base", "100"),
        "font_size_headings": get_config("font_size_headings", "100"),
        "font_size_table": get_config("font_size_table", "100"),
        "font_size_widgets": get_config("font_size_widgets", "100"),
    }
    # DB-URL für Anzeige (maskiert)
    from local_config import get_database_url as _get_db_url

    _raw_db = _get_db_url() or ""
    _db_masked = ""
    if _raw_db:
        try:
            from urllib.parse import urlparse as _up

            _p = _up(_raw_db)
            _db_masked = (
                _raw_db.replace(_p.password, "****") if _p.password else _raw_db
            )
        except Exception:
            _db_masked = _raw_db[:20] + "..." if len(_raw_db) > 20 else _raw_db
    return render_template(
        "admin_cms.html", cms=cms, demo_mode=is_demo_mode(), db_url_masked=_db_masked
    )


@app.route("/admin/cms/save", methods=["POST"])
@admin_required
def admin_cms_save():
    """Speichert CMS-Inhalte"""
    if not validate_csrf_token(request.form.get("csrf_token", "")):
        flash("Ungültiges Sicherheitstoken.", "error")
        return redirect(url_for("admin_cms"))

    section = request.form.get("section", "")

    if section == "login":
        from system_config import set_configs

        set_configs(
            {
                "login_title": request.form.get("login_title", "").strip(),
                "login_subtitle": request.form.get("login_subtitle", "").strip(),
                "login_notice": request.form.get("login_notice", "").strip(),
            },
            category="cms",
        )
        flash("Login-Texte gespeichert.", "success")

    elif section == "privacy":
        from system_config import set_config as _sc

        _sc(
            "cms_privacy_text",
            request.form.get("privacy_text", "").strip(),
            category="cms",
        )
        flash("Datenschutzerklärung gespeichert.", "success")

    elif section == "imprint":
        from system_config import set_config as _sc

        _sc(
            "cms_imprint_text",
            request.form.get("imprint_text", "").strip(),
            category="cms",
        )
        flash("Impressum gespeichert.", "success")

    elif section == "hints":
        from system_config import set_configs

        set_configs(
            {
                "dashboard_notice": request.form.get("dashboard_notice", "").strip(),
                "booking_notice": request.form.get("booking_notice", "").strip(),
            },
            category="cms",
        )
        flash("Hinweistexte gespeichert.", "success")

    elif section == "branding":
        import os as _os
        import base64

        from system_config import set_config as _sc2
        from system_config import set_configs as _scs

        _ALLOWED = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
        _os.makedirs(_os.path.join("static", "uploads"), exist_ok=True)

        logo_filename = get_config("logo_filename", "")
        if "logo_file" in request.files:
            f = request.files["logo_file"]
            if f and f.filename:
                ext = _os.path.splitext(f.filename)[1].lower()
                if ext in _ALLOWED:
                    # Save locally as a backup
                    local_logo = f"custom_logo{ext}"
                    f.save(_os.path.join("static", "uploads", local_logo))
                    
                    # Convert to base64 for database persistence
                    f.seek(0)
                    file_data = f.read()
                    encoded = base64.b64encode(file_data).decode("utf-8")
                    mime_type = f.content_type or f"image/{ext[1:]}"
                    if ext == ".svg":
                        mime_type = "image/svg+xml"
                    logo_filename = f"data:{mime_type};base64,{encoded}"
                else:
                    flash("Logo: Nur PNG, JPG, SVG oder WebP erlaubt.", "error")

        favicon_filename = get_config("favicon_filename", "")
        if "favicon_file" in request.files:
            f = request.files["favicon_file"]
            if f and f.filename:
                ext = _os.path.splitext(f.filename)[1].lower()
                if ext in _ALLOWED:
                    # Save locally as a backup
                    local_favicon = f"custom_favicon{ext}"
                    f.save(_os.path.join("static", "uploads", local_favicon))
                    
                    # Convert to base64 for database persistence
                    f.seek(0)
                    file_data = f.read()
                    encoded = base64.b64encode(file_data).decode("utf-8")
                    mime_type = f.content_type or f"image/{ext[1:]}"
                    if ext == ".svg":
                        mime_type = "image/svg+xml"
                    favicon_filename = f"data:{mime_type};base64,{encoded}"
                else:
                    flash("Favicon: Nur PNG, JPG, SVG oder WebP erlaubt.", "error")

        primary_color = request.form.get("primary_color", "#E91E63").strip()
        _scs(
            {
                "logo_filename": logo_filename,
                "favicon_filename": favicon_filename,
                "primary_color": primary_color,
            },
            category="branding",
        )
        flash("Branding gespeichert. ✅", "success")

    elif section == "dashboard":
        from system_config import set_configs

        set_configs(
            {
                "dashboard_title": request.form.get("dashboard_title", "").strip(),
                "help_content": request.form.get("help_content", "").strip(),
                "contact_name": request.form.get("contact_name", "").strip(),
                "contact_email": request.form.get("contact_email", "").strip(),
                "contact_phone": request.form.get("contact_phone", "").strip(),
                "contact_text": request.form.get("contact_text", "").strip(),
            },
            category="cms",
        )
        flash("Dashboard-Inhalte gespeichert.", "success")

    elif section == "smtp":
        from system_config import set_config as _sc
        from system_config import set_configs

        provider = request.form.get("email_provider", "smtp").strip()
        data = {
            "email_provider": provider,
            "admin_email": request.form.get("admin_email", "").strip(),
        }
        if provider == "resend":
            data["resend_api_key"] = request.form.get("resend_api_key", "").strip()
            data["resend_from"] = request.form.get("resend_from", "").strip()
        elif provider == "brevo":
            data["brevo_api_key"] = request.form.get("brevo_api_key", "").strip()
            data["brevo_from"] = request.form.get("brevo_from", "").strip()
            data["brevo_from_name"] = request.form.get("brevo_from_name", "").strip()
        else:
            data["smtp_host"] = request.form.get("smtp_host", "").strip()
            data["smtp_port"] = request.form.get("smtp_port", "587").strip()
            data["smtp_user"] = request.form.get("smtp_user", "").strip()
            data["smtp_tls"] = request.form.get("smtp_tls", "starttls").strip()
            data["smtp_from"] = request.form.get("smtp_from", "").strip()
            new_pass = request.form.get("smtp_pass", "").strip()
            if new_pass:
                _sc("smtp_pass", new_pass, category="smtp")
        set_configs(data, category="smtp")
        flash("E-Mail-Konfiguration gespeichert.", "success")

    elif section == "iserv":
        from system_config import set_configs

        new_admin_email = request.form.get("iserv_admin_email", "").strip()
        new_domain = request.form.get("iserv_domain", "").strip()
        new_client_id = request.form.get("iserv_client_id", "").strip()
        set_configs(
            {
                "iserv_admin_email": new_admin_email,
                "iserv_domain": new_domain,
                "iserv_client_id": new_client_id,
            },
            category="iserv",
        )
        # Client-Secret nur speichern wenn ausgefüllt
        new_secret = request.form.get("iserv_client_secret", "").strip()
        if new_secret:
            from system_config import set_config as _sc

            _sc("iserv_client_secret", new_secret, category="iserv")
        # Umgebungsvariablen sofort aktualisieren
        if new_admin_email:
            os.environ["ADMIN_EMAIL"] = new_admin_email
        if new_domain:
            os.environ["ISERV_DOMAIN"] = new_domain
        if new_client_id:
            os.environ["ISERV_CLIENT_ID"] = new_client_id
        invalidate_iserv_domain_cache()
        from oauth_config import reinit_oauth, _load_iserv_credentials
        global iserv_client, _registered_iserv_config
        iserv_client = reinit_oauth(app, oauth_instance)
        try:
            db_client_id, db_client_secret, db_domain = _load_iserv_credentials()
            _registered_iserv_config = {
                "client_id": db_client_id,
                "client_secret": db_client_secret,
                "domain": db_domain,
            }
        except Exception:
            pass
        flash("IServ-Konfiguration gespeichert. ✅", "success")

    elif section == "typography":
        from system_config import set_configs

        font_size_base = request.form.get("font_size_base", "100").strip()
        font_size_headings = request.form.get("font_size_headings", "100").strip()
        font_size_table = request.form.get("font_size_table", "100").strip()
        font_size_widgets = request.form.get("font_size_widgets", "100").strip()
        # Clamp values between 50 and 200
        try:
            font_size_base = str(max(50, min(200, int(font_size_base))))
            font_size_headings = str(max(50, min(200, int(font_size_headings))))
            font_size_table = str(max(50, min(200, int(font_size_table))))
            font_size_widgets = str(max(50, min(200, int(font_size_widgets))))
        except ValueError:
            font_size_base = font_size_headings = font_size_table = font_size_widgets = "100"
        set_configs(
            {
                "font_size_base": font_size_base,
                "font_size_headings": font_size_headings,
                "font_size_table": font_size_table,
                "font_size_widgets": font_size_widgets,
            },
            category="typography",
        )
        flash("Typografie-Einstellungen gespeichert. ✅", "success")

    elif section == "demo":
        from system_config import set_config as _sc

        enabled = "demo_mode_enabled" in request.form
        _sc("demo_mode", "true" if enabled else "false", category="system")
        flash(f"Demo-Modus {'aktiviert' if enabled else 'deaktiviert'}.", "success")

    elif section == "database":
        from local_config import set_database_url

        db_url = request.form.get("database_url", "").strip()
        if not db_url:
            flash("Keine URL eingegeben – Datenbank-Konfiguration unverändert.", "info")
            return redirect(url_for("admin_cms") + "#tab-database")
        # Verbindung testen
        try:
            import sqlalchemy as _sa

            _engine = _sa.create_engine(db_url, connect_args={"connect_timeout": 8})
            with _engine.connect() as _conn:
                _conn.execute(_sa.text("SELECT 1"))
            _engine.dispose()
        except Exception as e:
            flash(f"Verbindungstest fehlgeschlagen: {e}", "error")
            return redirect(url_for("admin_cms") + "#tab-database")
        set_database_url(db_url)
        _trigger_restart()
        return redirect(url_for("setup.restart_wait"))

    return redirect(url_for("admin_cms") + f"#tab-{section}")


# ── Werksreset ───────────────────────────────────────────────────────────────


@app.route("/admin/factory_reset", methods=["GET", "POST"])
@admin_required
def admin_factory_reset():
    """Werksreset: Buchungsdaten oder alles löschen."""
    if request.method == "POST":
        if not validate_csrf_token(request.form.get("csrf_token", "")):
            flash("Ungültiges Sicherheits-Token.", "error")
            return redirect(url_for("admin_factory_reset"))

        confirmation = request.form.get("confirmation", "").strip()
        mode = request.form.get("mode", "")

        if confirmation != "RESET":
            flash('Bestätigung falsch – bitte "RESET" eingeben.', "error")
            return redirect(url_for("admin_factory_reset"))

        if mode not in ("bookings", "full"):
            flash("Ungültiger Reset-Modus.", "error")
            return redirect(url_for("admin_factory_reset"))

        try:
            from models import (
                BlockedSlot,
                Booking,
                Course,
                Notification,
                Period,
                SchoolClass,
                SlotName,
                SystemConfig,
                User,
            )

            # Immer löschen: Benachrichtigungen, Buchungen, Sperren
            Notification.query.delete()
            Booking.query.delete()
            BlockedSlot.query.delete()

            if mode == "full":
                # Alle Nutzer löschen (kein hardcodierter Admin mehr)
                User.query.delete()
                # Alle Konfiguration außer Datenbank-URL löschen
                SystemConfig.query.filter(SystemConfig.category != "database").delete()
                # Kurse, Stunden, Schulklassen, Slot-Namen löschen
                Course.query.delete()
                Period.query.delete()
                SchoolClass.query.delete()
                SlotName.query.delete()

            db.session.commit()

            if mode == "full":
                # Session leeren, da der Admin-User gelöscht wurde
                session.clear()
                flash(
                    "✅ Vollständiger Werksreset abgeschlossen. Bitte richte das System neu ein.",
                    "success",
                )
                return redirect(url_for("setup.index"))
            else:
                flash(
                    "✅ Buchungsdaten erfolgreich gelöscht (Benutzer & Konfiguration bleiben erhalten).",
                    "success",
                )

        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Reset: {e}", "error")

        return redirect(url_for("admin"))

    return render_template("admin_factory_reset.html")


# Error-Handler für Production mit Fallback
@app.errorhandler(404)
def not_found_error(error):
    """Handler für 404 Not Found Fehler"""
    try:
        return render_template("errors/404.html"), 404
    except Exception:
        return (
            '<h1>404 - Seite nicht gefunden</h1><p><a href="/">Zur Startseite</a></p>',
            404,
        )


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
        return render_template("errors/500.html"), 500
    except Exception:
        return (
            "<h1>500 - Interner Serverfehler</h1><p>Bitte versuchen Sie es später erneut.</p>",
            500,
        )


@app.errorhandler(403)
def forbidden_error(error):
    """Handler für 403 Forbidden Fehler"""
    try:
        return render_template("errors/403.html"), 403
    except Exception:
        return (
            '<h1>403 - Zugriff verweigert</h1><p><a href="/">Zur Startseite</a></p>',
            403,
        )


# Logging-Konfiguration für Production
import logging
import os
from logging.handlers import RotatingFileHandler

if os.environ.get("FLASK_ENV") == "production" or not os.environ.get("FLASK_DEBUG"):
    if not os.path.exists("logs"):
        try:
            os.mkdir("logs")
        except OSError:
            pass

    try:
        file_handler = RotatingFileHandler(
            "logs/buchungssystem.log", maxBytes=10240000, backupCount=10
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("Buchungssystem gestartet (Production Mode)")
    except Exception as e:
        print(f"Fehler beim Einrichten des Logging-Handlers: {e}")


@app.route("/admin/factory-reset", methods=["POST"])
@admin_required
def factory_reset():
    """Löscht ALLE Daten und setzt das System auf Werkseinstellungen zurück."""
    if not validate_csrf_token(request.form.get("csrf_token", "")):
        flash("Ungültiges Sicherheitstoken.", "error")
        return redirect(url_for("admin_cms"))

    confirm_text = request.form.get("confirm_text", "").strip()
    confirm_check = request.form.get("confirm_check", "")

    if confirm_text != "RESET" or confirm_check != "1":
        flash(
            'Bestätigung fehlgeschlagen. Bitte geben Sie "RESET" ein und setzen Sie das Häkchen.',
            "error",
        )
        return redirect(url_for("admin_cms"))

    try:
        from models import (
            BlockedSlot,
            Booking,
            Course,
            Notification,
            Period,
            SchoolClass,
            SlotName,
            SystemConfig,
            User,
        )

        # Reihenfolge wichtig wegen Fremdschlüssel-Constraints
        Notification.query.delete()
        Booking.query.delete()
        BlockedSlot.query.delete()
        SlotName.query.delete()
        User.query.delete()
        Period.query.delete()
        Course.query.delete()
        SchoolClass.query.delete()
        SystemConfig.query.delete()  # letzt: löscht Konfiguration → Setup-Wizard startet neu

        from database import db as _db

        _db.session.commit()

        # Session leeren
        session.clear()

        app.logger.warning(
            "[FACTORY RESET] Alle Daten wurden gelöscht. System zurückgesetzt."
        )
        return redirect(url_for("setup.index"))

    except Exception as e:
        from database import db as _db

        _db.session.rollback()
        app.logger.error(f"[FACTORY RESET] Fehler beim Zurücksetzen: {e}")
        flash(f"Fehler beim Zurücksetzen: {e}", "error")
        return redirect(url_for("admin_cms"))


@app.route("/admin/test-resend", methods=["POST"])
@admin_required
def admin_test_resend():
    """Testet die Resend-E-Mail-Konfiguration."""
    if not validate_csrf_token(
        request.json.get("csrf_token", "") if request.json else ""
    ):
        return jsonify({"success": False, "message": "Ungültiges CSRF-Token."}), 403

    data = request.json or {}
    api_key = data.get("resend_api_key", "").strip()
    from_addr = data.get("resend_from", "").strip()
    test_email = data.get("test_email", "").strip()

    if not api_key or not from_addr or not test_email:
        return jsonify(
            {
                "success": False,
                "message": "API-Key, Absender-E-Mail und Test-Empfänger sind erforderlich.",
            }
        )

    try:
        import json as _json
        import urllib.error
        import urllib.request

        payload = {
            "from": from_addr,
            "to": [test_email],
            "subject": "✅ Resend-Test erfolgreich",
            "html": '<h2 style="color:#E91E63;">✅ Resend funktioniert!</h2><p>Diese Test-E-Mail wurde erfolgreich über die Resend-API verschickt.</p>',
        }
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.getcode() in (200, 201):
                return jsonify(
                    {
                        "success": True,
                        "message": f"Test-E-Mail erfolgreich an {test_email} gesendet!",
                    }
                )
            return jsonify(
                {
                    "success": False,
                    "message": f"Resend antwortete mit HTTP {resp.getcode()}.",
                }
            )
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        code = ""
        name = ""
        msg = body or str(e)

        try:
            err_data = _json.loads(body)
            code = err_data.get("statusCode") or err_data.get("code") or ""
            name = err_data.get("name", "")
            msg = err_data.get("message", "") or msg
        except Exception:
            pass

        # Bekannte Resend-Fehlercodes verständlich erklären
        lower_msg = msg.lower()
        lower_body = body.lower()
        if (
            "1010" in str(code)
            or "1010" in lower_body
            or "testing emails" in lower_msg
            or "only send" in lower_msg
            or "own email" in lower_msg
            or "validation_error" in name.lower()
            or (
                from_addr.lower() == "onboarding@resend.dev"
                and e.code == 403
                and "error code: 1010" in lower_body
            )
        ):
            import re as _re

            match = _re.search(r"\(([^)@]+@[^)]+)\)", msg)
            allowed_email = match.group(1) if match else None
            hint = (
                f" Die erlaubte Empfänger-E-Mail laut Resend: <strong>{allowed_email}</strong>"
                if allowed_email
                else " Nutze als Test-Empfänger genau die E-Mail-Adresse deines Resend-Kontos."
            )
            return jsonify(
                {
                    "success": False,
                    "message": "⚠️ Resend-Testmodus aktiv: Mit <code>onboarding@resend.dev</code> "
                    "kannst du nur an deine eigene Resend-Konto-E-Mail senden."
                    f"{hint} Für echten Versand an beliebige Adressen musst du in Resend "
                    "eine eigene Domain verifizieren und diese als Absender verwenden.",
                }
            )

        if "invalid_api_key" in name.lower() or e.code == 401:
            return jsonify(
                {
                    "success": False,
                    "message": '🔑 Ungültiger API-Key. Bitte prüfe den Key im Resend-Dashboard unter "API Keys". '
                    "Hinweis: Stelle sicher, dass der Key gespeichert (nicht nur eingegeben) wurde.",
                }
            )

        if msg and msg != body:
            return jsonify(
                {
                    "success": False,
                    "message": f"Resend Fehler ({name or e.code}): {msg}",
                }
            )

        return jsonify(
            {"success": False, "message": f"Resend HTTP {e.code}: {body or str(e)}"}
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Verbindungsfehler: {str(e)}"})


@app.route("/admin/test-brevo", methods=["POST"])
@admin_required
def admin_test_brevo():
    """Testet die Brevo-E-Mail-Konfiguration."""
    if not validate_csrf_token(
        request.json.get("csrf_token", "") if request.json else ""
    ):
        return jsonify({"success": False, "message": "Ungültiges CSRF-Token."}), 403

    data = request.json or {}
    api_key = data.get("brevo_api_key", "").strip()
    from_addr = data.get("brevo_from", "").strip()
    from_name = data.get("brevo_from_name", "").strip() or "SportOase"
    test_email = data.get("test_email", "").strip()

    if not api_key or not from_addr or not test_email:
        return jsonify(
            {
                "success": False,
                "message": "API-Key, Absender-E-Mail und Test-Empfänger sind erforderlich.",
            }
        )

    try:
        import json as _json
        import urllib.error
        import urllib.request

        payload = {
            "sender": {"email": from_addr, "name": from_name},
            "to": [{"email": test_email}],
            "subject": "✅ Brevo-Test erfolgreich",
            "htmlContent": '<h2>✅ Brevo funktioniert!</h2><p>Diese Test-E-Mail wurde erfolgreich über die Brevo-API verschickt.</p>',
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.getcode() in (200, 201, 202):
                return jsonify(
                    {
                        "success": True,
                        "message": f"Test-E-Mail erfolgreich an {test_email} gesendet!",
                    }
                )
            return jsonify(
                {
                    "success": False,
                    "message": f"Brevo antwortete mit HTTP {resp.getcode()}.",
                }
            )
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        msg = body or str(e)
        try:
            err_data = _json.loads(body)
            msg = err_data.get("message") or err_data.get("error", {}).get("message") or msg
        except Exception:
            pass

        return jsonify(
            {"success": False, "message": f"Brevo HTTP-Fehler {e.code}: {msg}"}
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Verbindungsfehler: {str(e)}"})


if __name__ == "__main__":
    # Starte die Anwendung
    app.run(host="0.0.0.0", port=5000, debug=True)
