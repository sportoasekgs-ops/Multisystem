# IServ OAuth2/OpenID Connect Konfiguration
# Credentials werden ZUERST aus der DB (Setup-Wizard) geladen, Env-Vars als Fallback.
# Rollen-/Gruppen-Scopes und Claims werden tolerant gegenüber alten und neuen IServ-Varianten verarbeitet.

import json
import os
import urllib.error
import urllib.request

from authlib.integrations.flask_client import OAuth


def _safe_str(value, default=""):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _get_config_or_env(config_key, env_key=None, default=""):
    value = None
    try:
        from system_config import get_config

        value = get_config(config_key)
    except Exception:
        value = None

    value = _safe_str(value)
    if value:
        return value

    if env_key:
        return _safe_str(os.environ.get(env_key, default), default)

    return _safe_str(default, default)


def _load_iserv_credentials():
    """
    Lädt IServ-Credentials: DB hat Vorrang, Env-Vars als Fallback.
    Gibt (client_id, client_secret, domain) zurück.
    """
    client_id = _get_config_or_env("iserv_client_id", "ISERV_CLIENT_ID", "")
    client_secret = _get_config_or_env("iserv_client_secret", "ISERV_CLIENT_SECRET", "")
    domain = _get_config_or_env("iserv_domain", "ISERV_DOMAIN", "")

    source = (
        "DB" if _safe_str(_get_config_or_env("iserv_client_id", None, "")) else "Env"
    )
    if client_id:
        print(f"[OAuth] Credentials geladen aus: {source} | Domain: {domain}")
    return client_id, client_secret, domain


def get_allowed_email_domain():
    """Gibt die erlaubte Mail-Domain für IServ-Logins zurück.

    Reihenfolge:
      1. DB: `iserv_email_domain`
      2. Env: `ISERV_EMAIL_DOMAIN`
      3. Fallback auf `iserv_domain` / `ISERV_DOMAIN`
    """
    domain = _get_config_or_env("iserv_email_domain", "ISERV_EMAIL_DOMAIN", "")
    if domain:
        return domain.lower()
    return _get_config_or_env("iserv_domain", "ISERV_DOMAIN", "").lower()


def _fetch_openid_metadata(iserv_domain):
    """Versucht OpenID-Metadaten von IServ zu laden, um kompatible Scopes zu bestimmen."""
    if not iserv_domain:
        return {}

    iserv_domain_clean = iserv_domain.replace("https://", "").replace("http://", "")
    base_url = iserv_domain if iserv_domain.startswith("http") else f"https://{iserv_domain}"
    
    urls = [
        f"{base_url}/.well-known/openid-configuration",
        f"{base_url}/iserv/public/.well-known/openid-configuration",
    ]

    last_error = None
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.getcode() != 200:
                    continue
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc

    if last_error:
        print(
            f"[OAuth] Hinweis: OpenID-Metadaten konnten nicht vorab geladen werden: {last_error}"
        )
    return {}


def _determine_requested_scopes(iserv_domain):
    """Ermittelt eine möglichst kompatible Scope-Liste für verschiedene IServ-Versionen."""
    metadata = _fetch_openid_metadata(iserv_domain)
    supported = set(metadata.get("scopes_supported") or [])

    scopes = ["openid", "profile", "email"]
    if supported:
        for candidate in ("roles", "groups", "iserv:roles", "iserv:groups"):
            if candidate in supported:
                scopes.append(candidate)
        print(
            f"[OAuth] Angeforderte Scopes laut Discovery: {' '.join(dict.fromkeys(scopes))}"
        )
    else:
        scopes.extend(["roles", "groups"])
        print(
            "[OAuth] Discovery-Scopes nicht verfügbar – Fallback auf: openid profile email roles groups"
        )

    return " ".join(dict.fromkeys(scopes))


def init_oauth(app):
    """
    Initialisiert OAuth2 mit IServ-Konfiguration.
    Gibt (oauth, iserv_client) zurück, wobei iserv_client None ist,
    wenn die Konfiguration fehlt.
    """
    oauth = OAuth(app)

    client_id, client_secret, iserv_domain = _load_iserv_credentials()

    if not client_id or not client_secret or not iserv_domain:
        print("=" * 70)
        print("⚠️  WARNUNG: IServ OAuth ist NICHT vollständig konfiguriert!")
        print(
            "   Bitte Domain, Client-ID und Client-Secret im Setup oder per Env setzen."
        )
        print("=" * 70)
        return oauth, None

    iserv_base_url = iserv_domain if iserv_domain.startswith("http") else f"https://{iserv_domain}"
    requested_scope = _determine_requested_scopes(iserv_domain)

    print("=" * 70)
    print("✅ IServ OAuth Konfiguration geladen")
    print(f"   Domain: {iserv_domain}")
    print(
        f"   Client ID: {client_id[:8]}...{client_id[-4:] if len(client_id) > 12 else ''}"
    )
    print(f"   Scopes: {requested_scope}")
    print("=" * 70)

    try:
        iserv = oauth.register(
            name="iserv",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=f"{iserv_base_url}/.well-known/openid-configuration",
            client_kwargs={"scope": requested_scope},
        )
        return oauth, iserv
    except Exception as e:
        print(f"❌ Fehler bei OAuth-Registrierung: {e}")
        return oauth, None


def reinit_oauth(app, oauth_instance):
    """
    Re-initialisiert den IServ OAuth-Client mit aktuellen DB-Werten.
    Wird nach dem Speichern der IServ-Konfiguration im Setup-Wizard aufgerufen.
    Gibt den neuen iserv_client zurück (oder None bei Fehler).
    """
    client_id, client_secret, iserv_domain = _load_iserv_credentials()

    if not client_id or not client_secret or not iserv_domain:
        return None

    try:
        # Entferne alten Client falls vorhanden
        if "iserv" in oauth_instance._clients:
            del oauth_instance._clients["iserv"]
    except Exception:
        pass

    requested_scope = _determine_requested_scopes(iserv_domain)

    try:
        iserv = oauth_instance.register(
            name="iserv",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=f"{iserv_domain if iserv_domain.startswith('http') else 'https://' + iserv_domain}/.well-known/openid-configuration",
            client_kwargs={"scope": requested_scope},
        )
        print(
            f"[OAuth] Re-Initialisierung erfolgreich (Domain: {iserv_domain}, Scopes: {requested_scope})"
        )
        return iserv
    except Exception as e:
        print(f"[OAuth] Re-Initialisierung fehlgeschlagen: {e}")
        return None


def get_admin_email():
    """Gibt die Admin-E-Mail zurück: DB hat Vorrang, dann Env-Var.
    Gibt leeren String zurück wenn keine Admin-E-Mail konfiguriert ist.
    """
    return _get_config_or_env("iserv_admin_email", "ADMIN_EMAIL", "")


def is_admin_email(email):
    """Prüft, ob die E-Mail-Adresse dem Admin gehört.
    Gibt False zurück wenn keine Admin-E-Mail konfiguriert ist.
    """
    admin = get_admin_email()
    if not admin or not email:
        return False
    return _safe_str(email).lower() == admin.lower()


def _append_membership_value(target, label, source_name, value):
    cleaned = _safe_str(value).lower()
    if cleaned and cleaned not in target:
        target.append(cleaned)
        print(f"   ✓ {label} ({source_name}): {value}")


def _extract_membership_values(data, label, field_names):
    values = []

    def handle_dict(item):
        for field_name in field_names:
            if field_name in item and isinstance(item[field_name], str):
                _append_membership_value(values, label, field_name, item[field_name])

    if isinstance(data, dict):
        if any(field_name in data for field_name in field_names):
            handle_dict(data)
        else:
            for item in data.values():
                if isinstance(item, dict):
                    handle_dict(item)
                elif isinstance(item, str):
                    _append_membership_value(values, label, "String value", item)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                handle_dict(item)
            elif isinstance(item, str):
                _append_membership_value(values, label, "String", item)
    elif isinstance(data, str):
        _append_membership_value(values, label, "einzelner String", data)

    return values


def extract_roles_from_userinfo(userinfo):
    """Extrahiert Rollennamen aus IServ userinfo (alt und neu)."""
    roles_key = next((key for key in ("roles", "iserv:roles") if key in userinfo), None)
    if not roles_key:
        print("   ⚠️ Kein 'roles' oder 'iserv:roles' Feld in userinfo gefunden")
        return []

    roles_data = userinfo[roles_key]
    print(f"   📋 Raw '{roles_key}' data: {roles_data}")
    return list(
        set(
            _extract_membership_values(
                roles_data, "Rolle", ("displayName", "name", "id")
            )
        )
    )


def extract_groups_from_userinfo(userinfo):
    """Extrahiert Gruppennamen aus IServ userinfo (alt und neu)."""
    groups_key = next(
        (key for key in ("groups", "iserv:groups") if key in userinfo), None
    )
    if not groups_key:
        print("   ⚠️ Kein 'groups' oder 'iserv:groups' Feld in userinfo gefunden")
        return []

    groups_data = userinfo[groups_key]
    print(f"   📋 Raw '{groups_key}' data: {groups_data}")
    return list(
        set(_extract_membership_values(groups_data, "Gruppe", ("name", "act", "id")))
    )


def determine_user_role(userinfo):
    """
    Bestimmt die Rolle des Benutzers basierend auf IServ-ROLLEN und GRUPPEN.

    Returns:
        Tuple: (role, iserv_role) wobei:
        - role: 'admin', 'teacher' oder None (kein Zugang)
        - iserv_role: Die erkannte IServ-Rolle/Gruppe
    """
    email = _safe_str(userinfo.get("email", "")).lower()

    print("=" * 70)
    print("🔐 IServ OAuth Login-Versuch")
    print(f"   E-Mail: {email}")
    print(f"   UserInfo Keys: {list(userinfo.keys())}")
    print("-" * 70)

    print("   📋 Komplette UserInfo:")
    for key, value in userinfo.items():
        value_str = str(value)
        if len(value_str) > 300:
            value_str = value_str[:300] + "..."
        print(f"      {key}: {value_str}")

    print("-" * 70)

    roles = extract_roles_from_userinfo(userinfo)
    groups = extract_groups_from_userinfo(userinfo)
    all_memberships = roles + groups

    print("-" * 70)
    print(f"   🏷️ Extrahierte Rollen: {roles}")
    print(f"   👥 Extrahierte Gruppen: {groups}")
    print(f"   📊 Kombinierte Mitgliedschaften: {all_memberships}")
    print("=" * 70)

    # 1. Admin-E-Mail hat immer Admin-Zugang
    if is_admin_email(email):
        print(f"   ✅ Admin erkannt (E-Mail-Match: {get_admin_email()})")
        return "admin", "Administrator"

    allowed_domain = get_allowed_email_domain()
    if allowed_domain and not email.endswith(f"@{allowed_domain}"):
        print(f"   ❌ KEIN ZUGANG - Keine @{allowed_domain} E-Mail")
        return None, None

    allowed_keywords = [
        "schulleitung",
        "role_school_management",
        "school_management",
        "lehrer",
        "lehrerin",
        "teacher",
        "role_teacher",
        "mitarbeitende",
        "mitarbeiter",
        "mitarbeiterin",
        "role_staff",
        "role_employee",
        "pädagogische mitarbeiter",
        "paedagogische mitarbeiter",
        "pädagogischer mitarbeiter",
        "role_educational_staff",
        "role_pedagogue",
        "sozialpädagog",
        "sozialpaedagog",
        "sozialpädagogin",
        "role_social_worker",
        "sekretariat",
        "verwaltung",
        "admins",
        "role_admin",
        "role_secretary",
        "administrator",
        "role_administrator",
    ]

    for membership in all_memberships:
        for allowed in allowed_keywords:
            if allowed in membership:
                display_role = membership.replace("_", " ").title()
                print(
                    f"   ✅ Zugang gewährt - Rolle/Gruppe erkannt: '{membership}' (matched '{allowed}')"
                )
                return "teacher", display_role

    blocked_keywords = [
        "schüler",
        "schueler",
        "schülerin",
        "schuelerin",
        "student",
        "students",
        "role_student",
    ]

    is_student_only = False
    for membership in all_memberships:
        for blocked in blocked_keywords:
            if blocked in membership:
                is_student_only = True
                print(f"   ⚠️ Schüler-Rolle/Gruppe erkannt: '{membership}'")
                break

    if is_student_only:
        print("   ❌ KEIN ZUGANG - Nur Schüler-Rolle gefunden")
        return None, None

    if all_memberships:
        print("   ❌ KEIN ZUGANG - Keine erlaubte Rolle/Gruppe gefunden")
    else:
        print("   ❌ KEIN ZUGANG - Keine Rollen/Gruppen in userinfo gefunden")

    return None, None
