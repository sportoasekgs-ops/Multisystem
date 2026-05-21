"""
Lokale Konfigurationsdatei (sportoase_local.json).
Wird VOR dem Datenbankstart gelesen – hier werden Einstellungen gespeichert,
die nicht in der Datenbank stehen können (z. B. die DATABASE_URL selbst).
"""

import json
import os

LOCAL_CONFIG_FILE = 'sportoase_local.json'


def _load() -> dict:
    """Liest die lokale Konfigurationsdatei. Gibt leeres Dict zurück wenn nicht vorhanden."""
    try:
        if os.path.exists(LOCAL_CONFIG_FILE):
            with open(LOCAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[LocalConfig] Fehler beim Lesen von {LOCAL_CONFIG_FILE}: {e}")
    return {}


def _save(data: dict) -> bool:
    """Schreibt die lokale Konfigurationsdatei."""
    try:
        with open(LOCAL_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[LocalConfig] Fehler beim Schreiben von {LOCAL_CONFIG_FILE}: {e}")
        return False


def get_local(key: str, default=None):
    """Liest einen Wert aus der lokalen Konfigurationsdatei."""
    return _load().get(key, default)


def set_local(key: str, value) -> bool:
    """Setzt einen Wert in der lokalen Konfigurationsdatei."""
    data = _load()
    data[key] = value
    return _save(data)


def get_database_url() -> str:
    """
    Gibt die Datenbank-URL zurück.
    Reihenfolge: Lokale Datei → Env-Var DATABASE_URL → Env-Var SQLALCHEMY_DATABASE_URI
    """
    local_url = get_local('database_url', '').strip()
    if local_url:
        print(f"[LocalConfig] DATABASE_URL aus lokaler Konfiguration geladen.")
        return local_url

    env_url = (
        os.environ.get('DATABASE_URL', '') or
        os.environ.get('SQLALCHEMY_DATABASE_URI', '')
    ).strip()
    if env_url:
        print(f"[LocalConfig] DATABASE_URL aus Umgebungsvariable geladen.")
    return env_url


def set_database_url(url: str) -> bool:
    """Speichert die Datenbank-URL in der lokalen Konfigurationsdatei."""
    return set_local('database_url', url.strip())


def is_database_configured() -> bool:
    """Gibt True zurück, wenn eine Datenbank-URL konfiguriert ist."""
    return bool(get_database_url())
