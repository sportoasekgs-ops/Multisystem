"""
Admin-Account anlegen (außerhalb der Webapp).
Aufruf:  python create_admin.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import app

def main():
    with app.app_context():
        from database import db
        from models import User
        from werkzeug.security import generate_password_hash

        db.create_all()

        print("=== Admin-Account anlegen ===")
        username = input("Benutzername: ").strip()
        if not username:
            print("Abgebrochen – kein Benutzername eingegeben.")
            return

        email = input("E-Mail (optional, Enter überspringen): ").strip()

        import getpass
        password = getpass.getpass("Passwort: ")
        if len(password) < 6:
            print("Fehler: Passwort muss mindestens 6 Zeichen haben.")
            return
        password2 = getpass.getpass("Passwort wiederholen: ")
        if password != password2:
            print("Fehler: Passwörter stimmen nicht überein.")
            return

        existing = User.query.filter_by(username=username).first()
        if existing:
            existing.password_hash = generate_password_hash(password)
            existing.role = 'admin'
            if email:
                existing.email = email
            db.session.commit()
            print(f"✅ Passwort für '{username}' aktualisiert (Rolle: admin).")
        else:
            u = User()
            u.username = username
            u.email = email or f"{username}@local"
            u.role = 'admin'
            u.password_hash = generate_password_hash(password)
            db.session.add(u)
            db.session.commit()
            print(f"✅ Admin-Account '{username}' erfolgreich angelegt.")

        print("\nLogin unter: /login  →  'Admin-Login (lokal)' klicken")

if __name__ == '__main__':
    main()
