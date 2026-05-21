# Skript zur Initialisierung der PostgreSQL-Datenbank
# Dieses Skript erstellt die Datenbank und legt einen Admin-Benutzer an

import os
from app import app
from models import create_user, get_user_by_username
from database import db

def setup_database():
    """Initialisiert die Datenbank und erstellt einen Standard-Admin-Account"""
    with app.app_context():
        print("Erstelle Datenbank-Tabellen...")
        db.create_all()
        print("Datenbank-Tabellen erfolgreich erstellt!")
        
        # Prüfe, ob bereits ein Admin existiert
        admin = get_user_by_username('sportoase')
        if not admin:
            # Erstelle Standard-Admin mit korrekter E-Mail
            admin_id = create_user('sportoase', 'mauro123', 'admin', 'sportoase.kg@gmail.com')
            if admin_id:
                print(f"\nAdmin-Account erstellt:")
                print(f"  Benutzername: sportoase")
                print(f"  Passwort: mauro123")
                print(f"  E-Mail: sportoase.kg@gmail.com")
            else:
                print("\nFehler: Admin-Account konnte nicht erstellt werden.")
        else:
            print("\nAdmin-Account existiert bereits.")
        
        print("\nDatenbank-Setup abgeschlossen!")
        print("Sie können sich jetzt mit den Admin-Zugangsdaten anmelden.")

if __name__ == '__main__':
    setup_database()
