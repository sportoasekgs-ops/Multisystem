# SportOase Buchungssystem

Web-Anwendung zur Verwaltung von Buchungen für die Schul-SportOase der KGS Pattensen (Ernst-Reuter-Schule).

## Funktionen

- **IServ SSO**: Login über IServ-Schulaccount (OAuth2/OpenID Connect)
- **Wochenplan-Anzeige**: Übersicht über feste und freie Zeitslots mit Farbkodierung
- **Buchungssystem**: Lehrkräfte können 1-5 Schüler pro Zeitslot anmelden
- **Kapazitätskontrolle**: Maximal 5 Schüler pro Zeitslot
- **Vorlaufzeit**: Buchungen nur bis 60 Minuten vor Stundenbeginn möglich
- **Meine Buchungen**: Eigene Buchungen einsehen, bearbeiten und löschen
- **E-Mail-Benachrichtigungen**: Automatische Benachrichtigung bei neuen Buchungen
- **Admin-Panel**: Verwaltung von Buchungen, Slot-Sperrungen und Benutzerübersicht
- **Mobile-optimiert**: Responsive Design mit 1-Tag-Ansicht auf Mobilgeräten

---

## Rollenverwaltung

| Rolle | Zugang |
|-------|--------|
| **Admin** | `morelli.maurizio@kgs-pattensen.de` oder IServ-Gruppe "Administrator" |
| **Lehrer** | IServ-Gruppen: Lehrer, Mitarbeitende, Mitarbeiter, Pädagogische Mitarbeiter, Sozialpädagogen, Beratung, Fairplaycoaches |

---

## Wochenplan-Struktur

| Stunde | Zeit |
|--------|------|
| 1. | 07:50 - 08:35 |
| 2. | 08:35 - 09:20 |
| 3. | 09:40 - 10:25 |
| 4. | 10:25 - 11:20 |
| 5. | 11:40 - 12:25 |
| 6. | 12:25 - 13:10 |

### Feste Angebote (farbkodiert)

- **Montag**: 1., 3., 5. Stunde fest
- **Dienstag**: Alle Stunden frei
- **Mittwoch**: 1., 3., 5. Stunde fest
- **Donnerstag**: 2., 5. Stunde fest
- **Freitag**: 2., 4., 5. Stunde fest

---

## Deployment auf Render

### 1. PostgreSQL-Datenbank erstellen

1. Render Dashboard → **New +** → **PostgreSQL**
2. Name: `sportoase-db`, Region: Frankfurt, Plan: Free
3. **Internal Database URL** kopieren
4. `postgres://` zu `postgresql://` ändern!

### 2. Web Service erstellen

| Einstellung | Wert |
|-------------|------|
| Name | `sportoase-app` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 main:app` |
| Python Version | 3.11 |

### 3. Environment Variables

| Variable | Beschreibung |
|----------|--------------|
| `DATABASE_URL` | PostgreSQL Connection String (postgresql://...) |
| `SESSION_SECRET` | Zufälliger 64-Zeichen-String |
| `ISERV_CLIENT_ID` | OAuth Client-ID aus IServ |
| `ISERV_CLIENT_SECRET` | OAuth Client-Secret aus IServ |
| `ISERV_DOMAIN` | `kgs-pattensen.de` |
| `SMTP_USER` | `sportoase.kgs@gmail.com` |
| `SMTP_PASS` | Gmail App-Passwort |

### 4. Datenbank initialisieren

```bash
# In Render Shell:
python db_setup.py
```

---

## IServ SSO Integration

### IServ-Admin-Konfiguration

1. **Verwaltung → System → Single-Sign-On**
2. Neue OAuth-App erstellen:
   - Name: `SportOase Buchungssystem`
   - Vertrauenswürdig: ✅ Ja
   - Redirect URI: `https://sportoase.app/oauth/callback`
   - Scopes: `openid`, `profile`, `email`

3. **Client-ID** und **Client-Secret** notieren
4. Benutzergruppen berechtigen: Administrator, Lehrer, Mitarbeitende

### OAuth-Endpunkte (IServ)

```
Authorization: https://kgs-pattensen.de/iserv/oauth/v2/auth
Token: https://kgs-pattensen.de/iserv/oauth/v2/token
UserInfo: https://kgs-pattensen.de/iserv/public/oauth/userinfo
```

---

## Projektstruktur

```
├── app.py                  # Haupt-Anwendung mit Routes
├── config.py               # Konfiguration (Stundenplan, SMTP)
├── models.py               # Datenbank-Modelle
├── db_setup.py             # Datenbank-Initialisierung
├── oauth_config.py         # IServ OAuth-Konfiguration
├── email_service.py        # E-Mail-Versand (SMTP)
├── templates/              # Jinja2 HTML-Templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── book.html
│   ├── meine_buchungen.html
│   ├── admin.html
│   └── ...
├── static/
│   ├── style.css
│   └── logo-ers.png
├── render.yaml             # Render Deployment Config
├── requirements.txt        # Python Dependencies
└── gunicorn_config.py      # Production Server Config
```

---

## Anpassungen

### Stundenplan ändern (`config.py`)

```python
PERIOD_TIMES = { ... }       # Zeiten der Schulstunden
FIXED_OFFERS = { ... }       # Feste Angebote pro Wochentag
FREE_MODULES = [ ... ]       # Module für freie Stunden
MAX_STUDENTS_PER_PERIOD = 5  # Max. Schüler pro Slot
BOOKING_ADVANCE_MINUTES = 60 # Vorlaufzeit in Minuten
```

---

## Troubleshooting

### App startet nicht
- Logs in Render Dashboard prüfen
- `DATABASE_URL` beginnt mit `postgresql://` (nicht `postgres://`)

### IServ Login funktioniert nicht
- Redirect URI in IServ korrekt: `https://sportoase.app/oauth/callback`
- Client-ID und Client-Secret korrekt kopiert
- `ISERV_DOMAIN` ohne `https://` (nur `kgs-pattensen.de`)

### E-Mails werden nicht gesendet
- Gmail App-Passwort verwenden (nicht normales Passwort)
- 2FA in Gmail aktiviert

### Datenbank-Fehler
- `python db_setup.py` in Render Shell ausführen

---

## Technologie-Stack

- **Backend**: Python 3.11, Flask, SQLAlchemy
- **Datenbank**: PostgreSQL (Neon auf Render)
- **Auth**: OAuth2/OpenID Connect (Authlib)
- **Server**: Gunicorn
- **Styling**: CSS mit Pink/Magenta-Theme (#E91E63)

---

## Support

- **E-Mail**: morelli.maurizio@kgs-pattensen.de
- **Telefon**: 0151 40349764
