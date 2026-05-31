# Slotra

**Zeitslots buchen – klar, flexibel, schulfertig.**

Slotra ist eine webbasierte Buchungsplattform für Schulen und pädagogische Angebote (z. B. SportOase, Förderstunden, AG-Slots, Raum- oder Kurszeiten). Lehrkräfte sehen auf einen Blick, was frei ist, buchen Schüler*innen in feste oder freie Zeitfenster – Admins behalten Kapazität, Regeln und Aussehen der gesamten Seite im Griff.

> **Hinweis:** Dieses Repository heißt historisch noch `Multisystem`. Das Produkt und die Oberfläche laufen unter dem Namen **Slotra**.

---

## Inhaltsverzeichnis

- [Warum Slotra?](#warum-slotra)
- [Funktionen](#funktionen)
- [Rollen & Rechte](#rollen--rechte)
- [Seiten-Designs (Themes)](#seiten-designs-themes)
- [Technologie](#technologie)
- [Projektstruktur](#projektstruktur)
- [Lokale Entwicklung](#lokale-entwicklung)
- [Ersteinrichtung (Setup-Wizard)](#ersteinrichtung-setup-wizard)
- [Deployment (Render)](#deployment-render)
- [Konfiguration](#konfiguration)
- [IServ-Anbindung](#iserv-anbindung)
- [Admin-Bereich](#admin-bereich)
- [Datenschutz](#datenschutz)
- [Fehlerbehebung](#fehlerbehebung)
- [Lizenz & Credits](#lizenz--credits)

---

## Warum Slotra?

| Problem im Schulalltag | Lösung mit Slotra |
|------------------------|-------------------|
| Zettel, Excel, E-Mail-Chaos bei Slot-Buchungen | Zentraler Wochenplan mit Live-Kapazität |
| Unklar, wer wann gebucht hat | „Meine Buchungen“ + Admin-Übersicht |
| Feste Kurse vs. freie Module | Farbige Slots, feste und freie Angebote konfigurierbar |
| Jede Schule sieht anders aus | Branding (Logo, Farben) + vier komplette Designs |
| DSGVO bei Schüler*innennamen | Namen gekürzt, fremde Buchungen verschleiert |

Der Name **Slotra** setzt sich aus **Slot** (Zeitfenster) und einer kurzen, merkfähigen Endung zusammen – als eigenständiger Markenname, nicht als bestehende Schul-Suite.

---

## Funktionen

### Für Lehrkräfte

- **Dashboard** mit Wochenübersicht (Desktop) und Tagesansicht (Mobil)
- **Buchung** von 1 bis *n* Schüler*innen pro Slot (Limit konfigurierbar)
- **Ganze Klasse** buchbar (ohne Einzelnamen)
- **Meine Buchungen**: ansehen, bearbeiten, löschen
- **Doppelbuchungs-Prüfung** und **Vorlaufzeit** (z. B. nur bis 60 Min. vor Stundenbeginn)
- **Exklusive Buchungen** mit Admin-Freigabe
- Hilfe, FAQ und Kontaktbox im Footer des Dashboards

### Für Admins

- **Admin-Cockpit**: Buchungen, Benutzer, Statistiken
- **Dynamische Konfiguration** (ohne Code-Deploy):
  - Unterrichtszeiten / Perioden (+ Vorlagen)
  - Kurse & Angebote (fest / frei)
  - Schulklassen
  - Buchungsregeln (Kapazität, Vorlaufzeit)
- **Slot-Namen** und **Ferien-Sperrung** (Bulk)
- **CMS**: Login-Texte, Dashboard-Hinweise, Datenschutz, Impressum
- **Branding**: Logo, Favicon, Primär-/Sekundär-/Hintergrundfarbe (Color Picker)
- **Seiten-Design** systemweit wählbar (siehe [Themes](#seiten-designs-themes))
- **SMTP** & **IServ OAuth** im Setup bzw. CMS
- **Externe Datenbank** konfigurierbar
- **Benachrichtigungen** (Glocke) bei neuen Vorgängen
- **Demo-Modus**, **Werksreset**, Auslastungsbericht

### System

- **Setup-Wizard** für die Erstinstallation
- **Hell/Dunkel-Modus** (pro Browser gespeichert)
- **E-Mail-Benachrichtigungen** bei Buchungen (SMTP)
- **CSRF-Schutz**, rollenbasierte Routen
- Responsives UI, Toast-Meldungen

---

## Rollen & Rechte

| Rolle | Typischer Zugang |
|-------|------------------|
| **Admin** | IServ-Gruppe „Administrator“ oder konfigurierter Admin-Account nach Setup |
| **Lehrkraft** | IServ-Gruppen (z. B. Lehrer, Mitarbeitende, Pädagogische Mitarbeitende – in `oauth_config.py` anpassbar) |

Admins sehen zusätzlich die Design-Auswahl in der Navigation und können das **systemweite** Erscheinungsbild für alle Nutzer speichern.

---

## Seiten-Designs (Themes)

Vier visuell **stark unterschiedliche** Designs – nicht nur andere Farben:

| Theme | Charakter |
|-------|-----------|
| **Klassisch** | Neo-Brutalist: kräftige Rahmen, versetzte Schatten, Poppins |
| **Professionell** | Corporate: Raster-Hintergrund, Inter, sachliche Tabellen |
| **Minimal** | Swiss: Schwarz-Weiß, eckig, Mono-Typografie – Branding als Akzent |
| **Elegant** | Glass / Serif: weiche Verläufe, Playfair Display, Blur-Karten |

**Farben** kommen immer aus dem CMS-Branding (Primär-, Sekundär-, Hintergrundfarbe). Layout und Typografie ändern sich pro Theme.

Speicherort: Datenbank (`system_config`, Schlüssel `admin_theme`). API: `POST /api/admin/theme`.

---

## Technologie

| Bereich | Stack |
|---------|--------|
| Backend | Python 3.11+, Flask |
| ORM | Flask-SQLAlchemy / SQLAlchemy 2 |
| Datenbank | PostgreSQL (Produktion), SQLite möglich (Entwicklung) |
| Auth | Authlib – OAuth2 / OpenID Connect (IServ) |
| Server | Gunicorn |
| Frontend | Jinja2-Templates, CSS Custom Properties, Vanilla JS |
| E-Mail | SMTP (z. B. Gmail mit App-Passwort) |

---

## Projektstruktur

```
├── main.py                 # Gunicorn-Einstieg: from app import app
├── app.py                  # Flask-App, Routen, Context Processors
├── models.py               # SQLAlchemy-Modelle (User, Booking, …)
├── database.py             # DB-Initialisierung
├── system_config.py        # Key-Value-Einstellungen in der DB
├── dynamic_config.py       # Stunden, Kurse, Klassen aus der DB
├── local_config.py         # buchungssystem_local.json (DATABASE_URL)
├── oauth_config.py         # IServ OAuth & Rollen-Mapping
├── email_service.py        # SMTP / Buchungs-Mails
├── admin_dynamic.py        # Blueprint: Perioden, Kurse, Klassen, Regeln
├── setup.py                # Blueprint: Setup-Wizard
├── demo_mode.py            # Demo-Daten ohne echte Buchungen
├── templates/              # HTML (base, dashboard, admin, setup, …)
│   └── partials/           # z. B. Theme-Picker
├── static/
│   ├── style.css           # Basis-UI
│   └── admin-themes.css    # Vier Slotra-Designs
├── requirements.txt
├── render.yaml             # Render.com Blueprint
├── .env.example            # Vorlage Umgebungsvariablen
└── mock_iserv_server.json  # Lokaler IServ-Mock (optional)
```

---

## Lokale Entwicklung

### Voraussetzungen

- Python 3.11+
- PostgreSQL **oder** SQLite (über Setup-Wizard / lokale JSON)

### Schnellstart

```bash
# Repository klonen
git clone https://github.com/sportoasekgs-ops/Multisystem.git
cd Multisystem

# Virtuelle Umgebung
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

# Umgebungsvariablen (mindestens SESSION_SECRET)
copy .env.example .env          # Windows
# cp .env.example .env

# SESSION_SECRET erzeugen (Beispiel)
python -c "import secrets; print(secrets.token_hex(32))"

# App starten
python -m flask --app app run --debug
# oder: python main.py  (wenn __main__ vorhanden) / flask run
```

Öffne `http://127.0.0.1:5000/setup` für den **Setup-Wizard** (Datenbank, Schule, Branding, SMTP, IServ, Admin).

### Lokale Datenbank-URL

Priorität:

1. `buchungssystem_local.json` (vom Wizard / Admin „Datenbank“)
2. Umgebungsvariable `DATABASE_URL`

---

## Ersteinrichtung (Setup-Wizard)

Unter `/setup` durchläufst du:

1. **Willkommen**
2. **Datenbank** (PostgreSQL-URL oder SQLite)
3. **Allgemeine Daten** (Schulname, …)
4. **Design & Branding** (Logo, Farben)
5. **E-Mail / SMTP**
6. **IServ OAuth**
7. **Admin-Account**
8. **Abgeschlossen**

Danach ist `setup_complete` in der DB gesetzt; normale Nutzer landen auf dem Login.

Grundeinstellungen später erneut öffnen: Admin → **Grundeinstellungen** (`/setup/reopen`).

---

## Deployment (Render)

`render.yaml` enthält Web-Service und PostgreSQL (Frankfurt).

### Web Service

| Einstellung | Wert |
|-------------|------|
| Build | `pip install -r requirements.txt` |
| Start | `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --preload main:app` |
| Python | 3.11 |

### Pflicht-Umgebungsvariablen

| Variable | Beschreibung |
|----------|--------------|
| `DATABASE_URL` | `postgresql://…` (bei Render oft `postgres://` → in `postgresql://` umwandeln) |
| `SESSION_SECRET` | Langer Zufallsstring (Render kann generieren) |
| `ISERV_CLIENT_ID` | OAuth Client-ID |
| `ISERV_CLIENT_SECRET` | OAuth Secret |
| `ISERV_DOMAIN` | Nur Domain, z. B. `kgs-pattensen.de` |
| `SMTP_USER` / `SMTP_PASS` | Optional, für Mailversand |

Nach dem Deploy einmal `/setup` aufrufen oder DB migrieren, falls bereits konfiguriert.

---

## Konfiguration

### In der Datenbank (`system_config`)

Z. B. Schulname, CMS-Texte, Branding-Farben, `admin_theme`, SMTP, IServ-IDs, Demo-Modus.

### Dynamisch im Admin (ohne Code)

- **Stunden** (`/admin/periods`)
- **Kurse** (`/admin/courses`)
- **Klassen** (`/admin/classes`)
- **Buchungs-Regeln** (`/admin/booking_settings`)

### Branding-Farben → Themes

Im CMS-Tab **Branding** legst du fest:

- **Primärfarbe** → Buttons, Akzente, Tabellenköpfe, Kontaktbox
- **Sekundärfarbe** → dunklere Variante / Hover
- **Hintergrundfarbe** → helle Flächen, Login-Hintergrund, Verläufe

Alle vier Themes nutzen diese Werte; das jeweilige Layout bleibt theme-spezifisch.

---

## IServ-Anbindung

1. IServ: **Verwaltung → System → Single Sign-On**
2. OAuth-App anlegen:
   - Redirect-URI: `https://<deine-domain>/oauth/callback`
   - Scopes: `openid`, `profile`, `email`
3. Client-ID und Secret in Slotra (Setup oder CMS) eintragen
4. Berechtigte Gruppen zuweisen

Typische Endpunkte (Domain anpassen):

```
https://<ISERV_DOMAIN>/iserv/oauth/v2/auth
https://<ISERV_DOMAIN>/iserv/oauth/v2/token
https://<ISERV_DOMAIN>/iserv/public/oauth/userinfo
```

Lokale Tests: `mock_iserv_server.py` / Mockoon-Konfiguration (`iserv_mockoon.json`).

---

## Admin-Bereich

| Bereich | Route (Auszug) |
|---------|----------------|
| Übersicht | `/admin` |
| Buchung anlegen / bearbeiten | `/admin/create_booking`, `/admin/edit_booking/<id>` |
| Slots umbenennen | `/admin/manage_slots` |
| Ferien-Sperrung | `/admin/bulk_block` |
| CMS & Branding | `/admin/cms` |
| Werksreset | `/admin/factory_reset` |
| Perioden / Kurse / Klassen / Regeln | `/admin/periods`, `/admin/courses`, … |
| Datenbank | `/admin/database_settings` |

---

## Datenschutz

- Schüler*innennamen in fremden Slots **gekürzt** (z. B. „Max M.“) bzw. **geblurrt**
- Eigene Buchungen voll sichtbar für die buchende Lehrkraft
- Datenschutz- und Impressumstexte über CMS pflegbar
- Session-Cookies mit `SESSION_SECRET` signiert

---

## Fehlerbehebung

| Symptom | Lösung |
|---------|--------|
| App startet nicht | `SESSION_SECRET` gesetzt? Logs prüfen |
| DB-Fehler | `DATABASE_URL` mit `postgresql://`; Setup erneut ausführen |
| IServ-Login scheitert | Redirect-URI exakt; Domain ohne `https://` |
| Keine E-Mails | Gmail-**App-Passwort**, SMTP in CMS testen |
| Design/Farben alt | Hard-Reload; Theme neu wählen (speichert in DB) |
| Setup-Loop | `system_config.setup_complete` prüfen |

---

## Lizenz & Credits

Entwickelt für den Schulbetrieb (u. a. KGS Pattensen / SportOase-Kontext).

- **Handcrafted by:** Mauro Morelli  
- Stack: Python, Flask, PostgreSQL, IServ OAuth  

Bei Fragen zur Installation oder Anpassung: Issues im GitHub-Repository oder Schul-IT.

---

**Slotra** – weil jeder Zeitslot zählt.
