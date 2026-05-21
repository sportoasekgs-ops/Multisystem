"""
Hilfsfunktionen für die System-Konfiguration (Key-Value-Store in der DB).
Alle App-Einstellungen werden hier gespeichert und gelesen.
"""

from database import db


def get_config(key, default=None):
    """Liest einen Konfigurations-Wert aus der Datenbank."""
    try:
        from models import SystemConfig
        entry = SystemConfig.query.filter_by(key=key).first()
        if entry is not None and entry.value is not None:
            return entry.value
        return default
    except Exception:
        return default


def set_config(key, value, category='general'):
    """Speichert einen Konfigurations-Wert in der Datenbank."""
    try:
        from models import SystemConfig
        from datetime import datetime
        entry = SystemConfig.query.filter_by(key=key).first()
        if entry:
            entry.value = str(value) if value is not None else None
            entry.category = category
            entry.updated_at = datetime.utcnow()
        else:
            entry = SystemConfig(key=key, value=str(value) if value is not None else None, category=category)
            db.session.add(entry)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[CONFIG] Fehler beim Speichern von '{key}': {e}")
        return False


def set_configs(data_dict, category='general'):
    """Speichert mehrere Konfigurations-Werte auf einmal."""
    try:
        from models import SystemConfig
        from datetime import datetime
        for key, value in data_dict.items():
            entry = SystemConfig.query.filter_by(key=key).first()
            if entry:
                entry.value = str(value) if value is not None else None
                entry.category = category
                entry.updated_at = datetime.utcnow()
            else:
                entry = SystemConfig(key=key, value=str(value) if value is not None else None, category=category)
                db.session.add(entry)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[CONFIG] Fehler beim Speichern mehrerer Werte: {e}")
        return False


def get_all_config(category=None):
    """Gibt alle Konfigurations-Werte als Dict zurück."""
    try:
        from models import SystemConfig
        if category:
            entries = SystemConfig.query.filter_by(category=category).all()
        else:
            entries = SystemConfig.query.all()
        return {e.key: e.value for e in entries}
    except Exception:
        return {}


def is_setup_complete():
    """Prüft ob der Setup-Wizard abgeschlossen wurde."""
    return get_config('setup_complete') == 'true'


def get_branding():
    """Gibt alle Branding-Werte zurück (mit Defaults)."""
    return {
        'school_name': get_config('school_name', ''),
        'school_subtitle': get_config('school_subtitle', 'Buchungssystem'),
        'primary_color': get_config('primary_color', '#E91E63'),
        'secondary_color': get_config('secondary_color', '#C2185B'),
        'logo_filename': get_config('logo_filename', ''),
        'favicon_filename': get_config('favicon_filename', ''),
        'background_color': get_config('background_color', '#fce4ec'),
    }
