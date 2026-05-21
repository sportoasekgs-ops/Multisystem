"""
Datenbank-Initialisierungsskript.
Der Admin-Account wird jetzt im Setup-Wizard (/setup/admin) angelegt –
nicht mehr mit hardcodierten Zugangsdaten.
"""

import os
from app import app
from database import db


def setup_database():
    """Initialisiert die Datenbank-Tabellen (ohne hardcodierten Admin)."""
    with app.app_context():
        print("Erstelle Datenbank-Tabellen...")
        db.create_all()
        print("Datenbank-Tabellen erfolgreich erstellt!")
        print("\nHinweis: Admin-Account bitte über den Setup-Wizard (/setup/admin) anlegen.")
        print("Datenbank-Setup abgeschlossen!")


if __name__ == '__main__':
    setup_database()
