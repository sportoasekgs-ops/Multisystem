"""
Setup-Wizard Blueprint für die Erstkonfiguration des Systems.
Schritt-für-Schritt-Einrichtung: Allgemeines → Branding → SMTP → IServ → Fertig
"""

import os
import secrets

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from system_config import (
    get_branding,
    get_config,
    is_setup_complete,
    set_config,
    set_configs,
)

setup_bp = Blueprint("setup", __name__, url_prefix="/setup")

STEPS = [
    {"id": "welcome", "title": "Willkommen", "icon": "👋"},
    {"id": "database", "title": "Datenbank", "icon": "🗄️"},
    {"id": "general", "title": "Allgemeine Daten", "icon": "🏫"},
    {"id": "branding", "title": "Design & Branding", "icon": "🎨"},
    {"id": "smtp", "title": "E-Mail / SMTP", "icon": "📧"},
    {"id": "iserv", "title": "IServ OAuth", "icon": "🔐"},
    {"id": "admin", "title": "Admin-Account", "icon": "👤"},
    {"id": "complete", "title": "Abgeschlossen", "icon": "✅"},
]

STEP_IDS = [s["id"] for s in STEPS]


def get_step_index(step_id):
    try:
        return STEP_IDS.index(step_id)
    except ValueError:
        return 0


def step_context(current_step_id):
    idx = get_step_index(current_step_id)
    return {
        "steps": STEPS,
        "current_step": current_step_id,
        "current_step_index": idx,
        "total_steps": len(STEPS),
        "progress_pct": int((idx / (len(STEPS) - 1)) * 100),
        "prev_step": STEP_IDS[idx - 1] if idx > 0 else None,
        "next_step": STEP_IDS[idx + 1] if idx < len(STEPS) - 1 else None,
    }


# ─── Startseite des Wizards ─────────────────────────────────────────────────


@setup_bp.route("/")
def index():
    return redirect(url_for("setup.step", step_id="welcome"))


@setup_bp.route("/restart-wait")
def restart_wait():
    """Warte-Seite nach dem Speichern der Datenbank-URL – zeigt Neustart-Animation."""
    return render_template("bootstrap_saved.html")


@setup_bp.route("/<step_id>", methods=["GET", "POST"])
def step(step_id):
    if step_id not in STEP_IDS:
        return redirect(url_for("setup.step", step_id="welcome"))

    # Wenn Setup bereits fertig, nur Admin darf zurückkehren
    # Im Bootstrap-Modus (keine echte DB) diesen Check überspringen,
    # da 'dashboard' dort nicht erreichbar ist und einen Redirect-Loop auslösen würde.
    from local_config import is_database_configured

    if is_setup_complete() and step_id != "complete" and is_database_configured():
        user_role = session.get("user_role")
        if user_role != "admin":
            return redirect(url_for("dashboard"))

    if request.method == "POST":
        return _handle_post(step_id)

    ctx = step_context(step_id)
    config = _get_step_config(step_id)
    return render_template(f"setup/{step_id}.html", **ctx, **config)


def _handle_post(step_id):
    """Verarbeitet POST-Requests für jeden Wizard-Schritt."""

    if step_id == "welcome":
        return redirect(url_for("setup.step", step_id="database"))

    elif step_id == "database":
        action = request.form.get("action", "save")
        if action == "skip":
            flash(
                "Datenbank-Schritt übersprungen – bestehende Konfiguration wird verwendet.",
                "info",
            )
            return redirect(url_for("setup.step", step_id="general"))

        from local_config import get_database_url, set_database_url

        db_url = request.form.get("database_url", "").strip()
        if db_url:
            set_database_url(db_url)
            try:
                from app import _trigger_restart

                _trigger_restart()
            except Exception:
                pass
            return redirect(url_for("setup.restart_wait"))
        else:
            flash(
                "Keine URL eingegeben – bestehende Konfiguration bleibt unverändert.",
                "info",
            )
        return redirect(url_for("setup.step", step_id="general"))

    elif step_id == "general":
        data = {
            "school_name": request.form.get("school_name", "").strip(),
            "school_subtitle": request.form.get("school_subtitle", "").strip(),
            "contact_name": request.form.get("contact_name", "").strip(),
            "contact_email": request.form.get("contact_email", "").strip(),
            "contact_phone": request.form.get("contact_phone", "").strip(),
            "school_address": request.form.get("school_address", "").strip(),
            "imprint_text": request.form.get("imprint_text", "").strip(),
            "privacy_text": request.form.get("privacy_text", "").strip(),
        }
        if not data["school_name"]:
            flash("Bitte gib einen Schulnamen ein.", "error")
            return redirect(url_for("setup.step", step_id="general"))
        set_configs(data, category="general")
        flash("Allgemeine Daten gespeichert.", "success")
        return redirect(url_for("setup.step", step_id="branding"))

    elif step_id == "branding":
        primary_color = request.form.get("primary_color", "#E91E63").strip()
        secondary_color = request.form.get("secondary_color", "#C2185B").strip()
        background_color = request.form.get("background_color", "#fce4ec").strip()

        # Logo-Upload
        logo_filename = get_config("logo_filename", "")
        if "logo_file" in request.files:
            f = request.files["logo_file"]
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
                    logo_filename = f"custom_logo{ext}"
                    save_path = os.path.join("static", "uploads", logo_filename)
                    f.save(save_path)
                else:
                    flash("Logo muss PNG, JPG, SVG oder WebP sein.", "error")

        # Favicon-Upload
        favicon_filename = get_config("favicon_filename", "")
        if "favicon_file" in request.files:
            f = request.files["favicon_file"]
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in (".png", ".ico", ".svg"):
                    favicon_filename = f"custom_favicon{ext}"
                    save_path = os.path.join("static", "uploads", favicon_filename)
                    f.save(save_path)

        set_configs(
            {
                "primary_color": primary_color,
                "secondary_color": secondary_color,
                "background_color": background_color,
                "logo_filename": logo_filename,
                "favicon_filename": favicon_filename,
            },
            category="branding",
        )
        flash("Design gespeichert.", "success")
        return redirect(url_for("setup.step", step_id="smtp"))

    elif step_id == "smtp":
        action = request.form.get("action", "save")
        if action == "skip":
            flash("E-Mail-Konfiguration übersprungen.", "info")
            return redirect(url_for("setup.step", step_id="iserv"))

        provider = request.form.get("email_provider", "smtp").strip()
        data = {
            "email_provider": provider,
            "admin_email": request.form.get("admin_email", "").strip(),
        }
        if provider == "resend":
            data["resend_api_key"] = request.form.get("resend_api_key", "").strip()
            data["resend_from"] = request.form.get("resend_from", "").strip()
        else:
            data["smtp_host"] = request.form.get("smtp_host", "").strip()
            data["smtp_port"] = request.form.get("smtp_port", "587").strip()
            data["smtp_user"] = request.form.get("smtp_user", "").strip()
            data["smtp_tls"] = request.form.get("smtp_tls", "starttls").strip()
            data["smtp_from"] = request.form.get("smtp_from", "").strip()
            # Passwort nur speichern wenn neu eingegeben
            smtp_pass = request.form.get("smtp_pass", "").strip()
            if smtp_pass:
                data["smtp_pass"] = smtp_pass
        set_configs(data, category="smtp")
        flash("E-Mail-Konfiguration gespeichert.", "success")
        return redirect(url_for("setup.step", step_id="iserv"))

    elif step_id == "iserv":
        action = request.form.get("action", "save")
        if action == "skip":
            flash(
                "IServ-Konfiguration übersprungen. Kann später eingerichtet werden.",
                "info",
            )
            return redirect(url_for("setup.step", step_id="admin"))

        iserv_domain = request.form.get("iserv_domain", "").strip()
        iserv_client_id = request.form.get("iserv_client_id", "").strip()
        iserv_client_secret = request.form.get("iserv_client_secret", "").strip()
        admin_email = request.form.get("admin_email", "").strip()

        if not iserv_domain or not iserv_client_id or not iserv_client_secret:
            flash(
                "Bitte fülle alle IServ-Felder aus oder überspringe diesen Schritt.",
                "error",
            )
            return redirect(url_for("setup.step", step_id="iserv"))

        if not admin_email:
            flash(
                "Bitte gib eine Admin-E-Mail-Adresse ein. Diese wird für den Admin-Zugang über IServ benötigt.",
                "error",
            )
            return redirect(url_for("setup.step", step_id="iserv"))

        set_configs(
            {
                "iserv_domain": iserv_domain,
                "iserv_client_id": iserv_client_id,
                "iserv_client_secret": iserv_client_secret,
                "iserv_admin_email": admin_email,
            },
            category="iserv",
        )

        # Auch als Umgebungsvariable im Prozess setzen (wirkt sofort)
        os.environ["ISERV_DOMAIN"] = iserv_domain
        os.environ["ISERV_CLIENT_ID"] = iserv_client_id
        os.environ["ISERV_CLIENT_SECRET"] = iserv_client_secret
        if admin_email:
            os.environ["ADMIN_EMAIL"] = admin_email

        try:
            from app import _trigger_restart

            _trigger_restart()
        except Exception:
            pass
        flash("IServ-Konfiguration gespeichert. App wird neu gestartet…", "success")
        return redirect(url_for("setup.restart_wait"))

    elif step_id == "admin":
        action = request.form.get("action", "save")
        if action == "skip":
            flash(
                "Admin-Account übersprungen – bitte stelle sicher, dass ein Admin-Zugang vorhanden ist.",
                "info",
            )
            return redirect(url_for("setup.step", step_id="complete"))

        username = request.form.get("admin_username", "").strip()
        password = request.form.get("admin_password", "").strip()
        password2 = request.form.get("admin_password2", "").strip()
        email = request.form.get("admin_email_local", "").strip()

        if not username or not password:
            flash("Benutzername und Passwort sind erforderlich.", "error")
            return redirect(url_for("setup.step", step_id="admin"))

        if password != password2:
            flash("Die Passwörter stimmen nicht überein.", "error")
            return redirect(url_for("setup.step", step_id="admin"))

        if len(password) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "error")
            return redirect(url_for("setup.step", step_id="admin"))

        try:
            from database import db
            from models import User, create_user

            existing = User.query.filter_by(username=username).first()
            if existing:
                existing.set_password(password)
                existing.role = "admin"
                if email:
                    existing.email = email
                db.session.commit()
                flash(f'Admin-Account "{username}" wurde aktualisiert.', "success")
            else:
                user_id = create_user(username, password, "admin", email or None)
                if user_id:
                    flash(
                        f'Admin-Account "{username}" erfolgreich erstellt.', "success"
                    )
                else:
                    flash("Fehler beim Erstellen des Admin-Accounts.", "error")
                    return redirect(url_for("setup.step", step_id="admin"))
        except Exception as e:
            flash(f"Fehler: {e}", "error")
            return redirect(url_for("setup.step", step_id="admin"))

        return redirect(url_for("setup.step", step_id="complete"))

    elif step_id == "complete":
        set_config("setup_complete", "true", category="system")
        flash("Setup abgeschlossen! Willkommen im System.", "success")
        return redirect(url_for("login"))

    return redirect(url_for("setup.step", step_id=step_id))


def _get_step_config(step_id):
    """Lädt gespeicherte Werte für das aktuelle Formular."""
    if step_id == "database":
        from local_config import get_local

        raw_url = get_local("database_url", "")
        db_configured = bool(raw_url)
        if raw_url:
            try:
                from urllib.parse import urlparse

                p = urlparse(raw_url)
                db_url_masked = f"{p.scheme}://***@{p.hostname}{p.path}"
            except Exception:
                db_url_masked = "(konfiguriert)"
        else:
            db_url_masked = ""
        return {
            "db_configured": db_configured,
            "db_url_masked": db_url_masked,
        }
    elif step_id == "general":
        return {
            "school_name": get_config("school_name", ""),
            "school_subtitle": get_config("school_subtitle", ""),
            "contact_name": get_config("contact_name", ""),
            "contact_email": get_config("contact_email", ""),
            "contact_phone": get_config("contact_phone", ""),
            "school_address": get_config("school_address", ""),
            "imprint_text": get_config("imprint_text", ""),
            "privacy_text": get_config("privacy_text", ""),
        }
    elif step_id == "branding":
        return {
            "primary_color": get_config("primary_color", "#E91E63"),
            "secondary_color": get_config("secondary_color", "#C2185B"),
            "background_color": get_config("background_color", "#fce4ec"),
            "logo_filename": get_config("logo_filename", ""),
            "favicon_filename": get_config("favicon_filename", ""),
        }
    elif step_id == "smtp":
        return {
            "email_provider": get_config("email_provider", "smtp"),
            "smtp_host": get_config("smtp_host", ""),
            "smtp_port": get_config("smtp_port", "587"),
            "smtp_user": get_config("smtp_user", ""),
            "smtp_pass": get_config("smtp_pass", ""),
            "smtp_tls": get_config("smtp_tls", "starttls"),
            "smtp_from": get_config("smtp_from", ""),
            "resend_api_key": get_config("resend_api_key", ""),
            "resend_from": get_config("resend_from", ""),
            "admin_email": get_config("admin_email", ""),
        }
    elif step_id == "iserv":
        return {
            "iserv_domain": get_config(
                "iserv_domain", os.environ.get("ISERV_DOMAIN", "")
            ),
            "iserv_client_id": get_config(
                "iserv_client_id", os.environ.get("ISERV_CLIENT_ID", "")
            ),
            "iserv_client_secret": get_config(
                "iserv_client_secret", os.environ.get("ISERV_CLIENT_SECRET", "")
            ),
            "iserv_admin_email": get_config("iserv_admin_email", ""),
        }
    elif step_id == "admin":
        try:
            from models import User

            admins = User.query.filter_by(role="admin").all()
            existing_admins = [
                {"username": u.username, "email": u.email or ""} for u in admins
            ]
        except Exception:
            existing_admins = []
        return {"existing_admins": existing_admins}
    elif step_id == "complete":
        return {
            "school_name": get_config("school_name", "Ihre Einrichtung"),
            "iserv_domain": get_config("iserv_domain", ""),
            "smtp_host": get_config("smtp_host", ""),
            "logo_filename": get_config("logo_filename", ""),
            "primary_color": get_config("primary_color", "#E91E63"),
        }
    return {}


# ─── AJAX: SMTP-Test ────────────────────────────────────────────────────────


@setup_bp.route("/test-smtp", methods=["POST"])
def test_smtp():
    """Sendet eine Test-E-Mail über die eingegebenen SMTP-Daten."""
    data = request.get_json(silent=True) or {}
    host = data.get("smtp_host", "").strip()
    port = int(data.get("smtp_port", 587) or 587)
    user = data.get("smtp_user", "").strip()
    password = data.get("smtp_pass", "").strip()
    tls_mode = data.get("smtp_tls", "starttls")
    recipient = (data.get("test_email", "") or "").strip() or user

    # Wenn kein Passwort eingegeben, gespeichertes aus DB verwenden
    if not password and data.get("use_saved_pass"):
        password = (get_config("smtp_pass", "") or "").strip()
    # Wenn kein Host/User/Port vom Client, aus DB laden
    if not host:
        host = (get_config("smtp_host", "") or "").strip()
    if not user:
        user = (get_config("smtp_user", "") or "").strip()
    if not password:
        password = (get_config("smtp_pass", "") or "").strip()

    if not host or not user or not password:
        return jsonify(
            {
                "success": False,
                "message": "Host, Benutzer und Passwort sind erforderlich.",
            }
        )

    try:
        import smtplib
        import socket as _socket
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        # IPv4 erzwingen (verhindert errno 101 "Network is unreachable" bei IPv6-Problemen)
        try:
            ipv4 = _socket.getaddrinfo(
                host, port, _socket.AF_INET, _socket.SOCK_STREAM
            )[0][4][0]
        except Exception:
            ipv4 = host

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ SMTP-Test erfolgreich"
        msg["From"] = user
        msg["To"] = recipient

        html = """
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:30px;">
            <h2 style="color:#E91E63;">✅ SMTP-Test erfolgreich!</h2>
            <p>Diese E-Mail wurde über deine SMTP-Konfiguration gesendet.</p>
            <p style="color:#666;font-size:13px;">Buchungssystem Setup-Wizard</p>
        </div>"""
        msg.attach(MIMEText(html, "html", "utf-8"))

        if tls_mode == "ssl":
            with smtplib.SMTP_SSL(ipv4, port, timeout=10) as server:
                server.login(user, password)
                server.sendmail(user, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(ipv4, port, timeout=10) as server:
                server.ehlo()
                if tls_mode == "starttls":
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
                server.sendmail(user, [recipient], msg.as_string())

        return jsonify(
            {
                "success": True,
                "message": f"Test-E-Mail erfolgreich an {recipient} gesendet!",
            }
        )

    except Exception as e:
        err = str(e)
        # Bekannte Fehler verständlich erklären
        if "5.7.139" in err or "basic authentication is disabled" in err.lower():
            return jsonify(
                {
                    "success": False,
                    "message": "🔒 Microsoft hat Basic Authentication deaktiviert. "
                    "Normales Passwort funktioniert nicht mehr mit Outlook/Office365. "
                    "Lösung: App-Passwort erstellen (Microsoft-Konto → Sicherheit → "
                    "Erweiterte Sicherheit → App-Passwörter) – oder Resend als "
                    "E-Mail-Provider verwenden.",
                    "error_type": "ms_basic_auth",
                }
            )
        if "5.7.57" in err or "client not authenticated" in err.lower():
            return jsonify(
                {
                    "success": False,
                    "message": "🔒 Authentifizierung fehlgeschlagen. Bei Microsoft 365 Schulkonten "
                    "muss SMTP AUTH vom IT-Administrator explizit aktiviert werden "
                    "(Exchange Admin Center → Postfach → SMTP AUTH aktivieren).",
                    "error_type": "ms_auth",
                }
            )
        if "Name or service not known" in err or "nodename nor servname" in err:
            return jsonify(
                {
                    "success": False,
                    "message": f'🌐 Hostname nicht gefunden: „{host}". '
                    "Bitte SMTP-Host prüfen – z.B. smtp-mail.outlook.com (Outlook) "
                    "oder smtp.gmail.com (Gmail).",
                    "error_type": "hostname",
                }
            )
        if "timed out" in err.lower() or "Connection refused" in err:
            return jsonify(
                {
                    "success": False,
                    "message": f"⏱️ Verbindung zu {host}:{port} fehlgeschlagen. "
                    "Port oder Firewall-Einstellungen prüfen.",
                    "error_type": "connection",
                }
            )
        return jsonify({"success": False, "message": f"Fehler: {err}"})


# ─── AJAX: Datenbank-Test ───────────────────────────────────────────────────


@setup_bp.route("/test-db", methods=["POST"])
def test_db():
    """Testet eine PostgreSQL-Verbindung mit der angegebenen URL."""
    data = request.get_json(silent=True) or {}
    db_url = data.get("database_url", "").strip()

    if not db_url:
        return jsonify(
            {"success": False, "message": "Bitte eine Datenbank-URL eingeben."}
        )

    try:
        import sqlalchemy

        engine = sqlalchemy.create_engine(db_url, connect_args={"connect_timeout": 8})
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        engine.dispose()
        return jsonify(
            {
                "success": True,
                "message": "Verbindung erfolgreich! Datenbank ist erreichbar.",
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Verbindung fehlgeschlagen: {str(e)}"}
        )


# ─── Setup von Admin erneut aufrufen ────────────────────────────────────────


@setup_bp.route("/reopen")
def reopen():
    """Erlaubt Admin, den Setup-Wizard erneut aufzurufen."""
    if session.get("user_role") != "admin":
        flash("Nur Admins können den Setup-Wizard erneut aufrufen.", "error")
        return redirect(url_for("dashboard"))
    return redirect(url_for("setup.step", step_id="database"))
