# IServ OAuth2/OpenID Connect Konfiguration
# Credentials werden ZUERST aus der DB (Setup-Wizard) geladen, Env-Vars als Fallback

import os
import json
from authlib.integrations.flask_client import OAuth


def _load_iserv_credentials():
    """
    Lädt IServ-Credentials: DB hat Vorrang, Env-Vars als Fallback.
    Gibt (client_id, client_secret, domain) zurück.
    """
    try:
        from system_config import get_config
        db_client_id     = get_config('iserv_client_id', '').strip()
        db_client_secret = get_config('iserv_client_secret', '').strip()
        db_domain        = get_config('iserv_domain', '').strip()
    except Exception:
        db_client_id = db_client_secret = db_domain = ''

    client_id     = db_client_id     or os.environ.get('ISERV_CLIENT_ID', '').strip()
    client_secret = db_client_secret or os.environ.get('ISERV_CLIENT_SECRET', '').strip()
    domain        = db_domain        or os.environ.get('ISERV_DOMAIN', '').strip()

    source = 'DB' if db_client_id else 'Env'
    if client_id:
        print(f"[OAuth] Credentials geladen aus: {source} | Domain: {domain}")
    return client_id, client_secret, domain


def init_oauth(app):
    """
    Initialisiert OAuth2 mit IServ-Konfiguration.
    Gibt (oauth, iserv_client) zurück, wobei iserv_client None ist,
    wenn die Konfiguration fehlt.
    """
    oauth = OAuth(app)

    client_id, client_secret, iserv_domain = _load_iserv_credentials()

    if not client_id or not client_secret:
        print("=" * 70)
        print("⚠️  WARNUNG: IServ OAuth ist NICHT konfiguriert!")
        print("   Bitte in Setup-Wizard (Admin → Einstellungen) oder")
        print("   als Umgebungsvariable (ISERV_CLIENT_ID / ISERV_CLIENT_SECRET) eintragen.")
        print("=" * 70)
        return oauth, None

    iserv_base_url = f'https://{iserv_domain}'

    print("=" * 70)
    print("✅ IServ OAuth Konfiguration geladen")
    print(f"   Domain: {iserv_domain}")
    print(f"   Client ID: {client_id[:8]}...{client_id[-4:] if len(client_id) > 12 else ''}")
    print("=" * 70)

    try:
        iserv = oauth.register(
            name='iserv',
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=f'{iserv_base_url}/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid profile email roles groups'}
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

    if not client_id or not client_secret:
        return None

    try:
        # Entferne alten Client falls vorhanden
        if 'iserv' in oauth_instance._clients:
            del oauth_instance._clients['iserv']
    except Exception:
        pass

    try:
        iserv = oauth_instance.register(
            name='iserv',
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=f'https://{iserv_domain}/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid profile email roles groups'}
        )
        print(f"[OAuth] Re-Initialisierung erfolgreich (Domain: {iserv_domain})")
        return iserv
    except Exception as e:
        print(f"[OAuth] Re-Initialisierung fehlgeschlagen: {e}")
        return None


def get_admin_email():
    """Gibt die Admin-E-Mail zurück: DB hat Vorrang, dann Env-Var.
    Gibt leeren String zurück wenn keine Admin-E-Mail konfiguriert ist.
    """
    try:
        from system_config import get_config
        db_email = get_config('iserv_admin_email', '').strip()
        if db_email:
            return db_email
    except Exception:
        pass
    return os.environ.get('ADMIN_EMAIL', '').strip()


def is_admin_email(email):
    """Prüft, ob die E-Mail-Adresse dem Admin gehört.
    Gibt False zurück wenn keine Admin-E-Mail konfiguriert ist.
    """
    admin = get_admin_email()
    if not admin or not email:
        return False
    return email.lower().strip() == admin.lower()


def extract_roles_from_userinfo(userinfo):
    """
    Extrahiert Rollennamen aus IServ userinfo.

    IServ-Format (tatsächlich beobachtet):
    {
        "roles": [
            {"uuid": "...", "id": "ROLE_SCHOOL_MANAGEMENT", "displayName": "Schulleitung"},
            {"uuid": "...", "id": "ROLE_USER", "displayName": "Benutzer"}
        ]
    }

    Gibt eine Liste von Rollennamen zurück (lowercase).
    """
    roles = []

    if 'roles' in userinfo:
        roles_data = userinfo['roles']
        print(f"   📋 Raw 'roles' data: {roles_data}")

        if isinstance(roles_data, list):
            for role_item in roles_data:
                if isinstance(role_item, dict):
                    if 'displayName' in role_item and isinstance(role_item['displayName'], str):
                        display_name = role_item['displayName'].lower().strip()
                        roles.append(display_name)
                        print(f"   ✓ Rolle (displayName): {role_item['displayName']}")
                    if 'name' in role_item and isinstance(role_item['name'], str):
                        role_name = role_item['name'].lower().strip()
                        if role_name not in roles:
                            roles.append(role_name)
                            print(f"   ✓ Rolle (name): {role_item['name']}")
                    if 'id' in role_item and isinstance(role_item['id'], str):
                        role_id = role_item['id'].lower().strip()
                        roles.append(role_id)
                        print(f"   ✓ Rolle (id): {role_item['id']}")
                elif isinstance(role_item, str):
                    roles.append(role_item.lower().strip())
                    print(f"   ✓ Rolle (String): {role_item}")
        elif isinstance(roles_data, str):
            roles.append(roles_data.lower().strip())
            print(f"   ✓ Rolle (einzelner String): {roles_data}")
    else:
        print(f"   ⚠️ Kein 'roles' Feld in userinfo gefunden")

    return list(set(r for r in roles if r))


def extract_groups_from_userinfo(userinfo):
    """
    Extrahiert Gruppennamen aus IServ userinfo.

    IServ-Format (tatsächlich beobachtet - Dictionary mit IDs als Keys):
    {
        "groups": {
            "2235": {"id": 2235, "uuid": "...", "act": "schulleitung", "name": "Schulleitung"}
        }
    }

    Gibt eine Liste von Gruppennamen zurück (lowercase).
    """
    groups = []

    if 'groups' in userinfo:
        groups_data = userinfo['groups']
        print(f"   📋 Raw 'groups' data: {groups_data}")

        if isinstance(groups_data, dict):
            for group_key, group_item in groups_data.items():
                if isinstance(group_item, dict):
                    if 'name' in group_item and isinstance(group_item['name'], str):
                        groups.append(group_item['name'].lower().strip())
                        print(f"   ✓ Gruppe (name): {group_item['name']}")
                    if 'act' in group_item and isinstance(group_item['act'], str):
                        act_value = group_item['act'].lower().strip()
                        if act_value not in groups:
                            groups.append(act_value)
                            print(f"   ✓ Gruppe (act): {group_item['act']}")
                elif isinstance(group_item, str):
                    groups.append(group_item.lower().strip())
                    print(f"   ✓ Gruppe (String value): {group_item}")
        elif isinstance(groups_data, list):
            for group_item in groups_data:
                if isinstance(group_item, dict):
                    if 'name' in group_item and isinstance(group_item['name'], str):
                        groups.append(group_item['name'].lower().strip())
                        print(f"   ✓ Gruppe (name): {group_item['name']}")
                    if 'act' in group_item and isinstance(group_item['act'], str):
                        groups.append(group_item['act'].lower().strip())
                        print(f"   ✓ Gruppe (act): {group_item['act']}")
                elif isinstance(group_item, str):
                    groups.append(group_item.lower().strip())
                    print(f"   ✓ Gruppe (String): {group_item}")
        elif isinstance(groups_data, str):
            groups.append(groups_data.lower().strip())
            print(f"   ✓ Gruppe (einzelner String): {groups_data}")
    else:
        print(f"   ⚠️ Kein 'groups' Feld in userinfo gefunden")

    return list(set(g for g in groups if g))


def determine_user_role(userinfo):
    """
    Bestimmt die Rolle des Benutzers basierend auf IServ-ROLLEN und GRUPPEN.

    Returns:
        Tuple: (role, iserv_role) wobei:
        - role: 'admin', 'teacher' oder None (kein Zugang)
        - iserv_role: Die erkannte IServ-Rolle/Gruppe
    """
    email = userinfo.get('email', '').lower().strip()

    print("=" * 70)
    print(f"🔐 IServ OAuth Login-Versuch")
    print(f"   E-Mail: {email}")
    print(f"   UserInfo Keys: {list(userinfo.keys())}")
    print("-" * 70)

    print(f"   📋 Komplette UserInfo:")
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
        return 'admin', 'Administrator'

    # Prüfe E-Mail-Domain (aus DB oder Env)
    try:
        from system_config import get_config
        allowed_domain = get_config('iserv_domain', '').strip() or os.environ.get('ISERV_DOMAIN', '').strip()
    except Exception:
        allowed_domain = os.environ.get('ISERV_DOMAIN', '').strip()

    if allowed_domain and not email.endswith(f'@{allowed_domain}'):
        print(f"   ❌ KEIN ZUGANG - Keine @{allowed_domain} E-Mail")
        return None, None

    allowed_keywords = [
        'schulleitung', 'role_school_management', 'school_management',
        'lehrer', 'lehrerin', 'teacher', 'role_teacher',
        'mitarbeitende', 'mitarbeiter', 'mitarbeiterin', 'role_staff', 'role_employee',
        'pädagogische mitarbeiter', 'paedagogische mitarbeiter',
        'pädagogischer mitarbeiter', 'role_educational_staff', 'role_pedagogue',
        'sozialpädagog', 'sozialpaedagog', 'sozialpädagogin', 'role_social_worker',
        'sekretariat', 'verwaltung', 'admins', 'role_admin', 'role_secretary',
        'administrator', 'role_administrator',
    ]

    for membership in all_memberships:
        for allowed in allowed_keywords:
            if allowed in membership:
                display_role = membership.replace('_', ' ').title()
                print(f"   ✅ Zugang gewährt - Rolle/Gruppe erkannt: '{membership}' (matched '{allowed}')")
                return 'teacher', display_role

    blocked_keywords = [
        'schüler', 'schueler', 'schülerin', 'schuelerin',
        'student', 'students', 'role_student',
    ]

    is_student_only = False
    for membership in all_memberships:
        for blocked in blocked_keywords:
            if blocked in membership:
                is_student_only = True
                print(f"   ⚠️ Schüler-Rolle/Gruppe erkannt: '{membership}'")
                break

    if is_student_only:
        print(f"   ❌ KEIN ZUGANG - Nur Schüler-Rolle gefunden")
        return None, None

    if all_memberships:
        print(f"   ❌ KEIN ZUGANG - Keine erlaubte Rolle/Gruppe gefunden")
    else:
        print(f"   ❌ KEIN ZUGANG - Keine Rollen/Gruppen in userinfo gefunden")

    return None, None
