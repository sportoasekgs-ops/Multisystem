# SportOase Buchungssystem

## Overview

SportOase Buchungssystem is a web-based booking management system for the school sports facility (SportOase) at KGS Pattensen (Ernst-Reuter-Schule). Teachers can book time slots for 1-5 students, view a color-coded weekly schedule, and manage their own bookings. Administrators have full control over all bookings, slot blocking, and user management. Authentication is handled via IServ SSO (OAuth2/OpenID Connect).

## User Preferences

- Communication style: Simple, everyday language (German)
- Design: Pink/Magenta color scheme (#E91E63) matching ERS school branding
- Mobile-first: 1-day scrollable view on mobile, 5-day view on desktop

## System Architecture

### Frontend

- **Templates**: Jinja2 (Flask) with base template for consistent layout
- **Design**: Modern card-based UI with color-coded course slots
- **Responsive**: Mobile-optimized with 1-day horizontal scroll view
- **Key Pages**: Login, Dashboard (weekly overview), Booking form, Meine Buchungen, Admin panel

### Backend

- **Framework**: Flask (Python 3.11)
- **Authentication**: IServ SSO (OAuth2/OpenID Connect via Authlib)
- **Authorization**: Role-based (`@login_required`, `@admin_required`)
- **Timezone**: Europe/Berlin (pytz)

### File Structure

```
├── app.py              # Main application routes
├── config.py           # Schedule, SMTP, settings
├── models.py           # Database models (SQLAlchemy)
├── database.py         # Database instance
├── db_setup.py         # Database initialization
├── oauth_config.py     # IServ OAuth configuration
├── email_service.py    # SMTP email notifications
├── templates/          # Jinja2 HTML templates
├── static/             # CSS, logos
├── render.yaml         # Render deployment config
└── requirements.txt    # Python dependencies
```

### Data Storage

- **Database**: PostgreSQL (Neon-backed via Replit, Render in production)
- **ORM**: Flask-SQLAlchemy 3.1.1
- **Tables**: users, bookings, slot_names, blocked_slots, notifications

### Authentication & Authorization

**IServ SSO**: OAuth2/OpenID Connect integration (Scope: `openid profile email roles`)

**Admin-Zugang**:
- E-Mail: `morelli.maurizio@kgs-pattensen.de` (immer Admin)

**Lehrer-Zugang** (basierend auf IServ-ROLLEN):
- Schulleitung
- Lehrer / Lehrerin
- Sozialpädagogen / Sozialpädagogin
- Pädagogische Mitarbeiter
- Mitarbeiter / Mitarbeiterin

**Kein Zugang**:
- Schüler (automatisch blockiert)
- Alle anderen Rollen

**App-Rechte**:
- **Teachers**: Create bookings, edit/delete own bookings (up to 1 hour before)
- **Admins**: Full access, no time restrictions

### Key Features

- **Color-coded Slots**: Each course type has unique color and icon tag
- **Today Highlighting**: Current day visually distinguished in week view
- **Meine Buchungen**: Teachers view/edit/delete their own bookings
- **Slot Blocking**: Admins can bulk-block slots for holidays
- **CSRF Protection**: All POST requests protected
- **E-Mail Notifications**: SMTP-based booking confirmations

### Course Colors & Tags

| Course | Color | Tag |
|--------|-------|-----|
| Wochenstart-Aktivierung | Orange | ☀️ Energie |
| Konflikt-Reset | Violet | 🛡️ Reset |
| Koordinationszirkel | Blue | 🎯 Fokus |
| Sozialtraining | Teal | 👥 Team |
| Mini-Fitness | Green | ⚡ Power |
| Motorik-Parcours | Orange | 🏃 Bewegung |
| Turnen + Balance | Pink | 🤸 Balance |
| Atem & Reflexion | Cyan | 🌬️ Atem |
| Bodyscan Light | Purple | 🧘 Scan |
| Ruhezone | Mint | 🍃 Ruhe |
| Freie Wahl | Gray | ⭐ Flexibel |

## Environment Variables

| Variable | Description | Location |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Render |
| `SESSION_SECRET` | Flask session secret (required) | Replit + Render |
| `ISERV_CLIENT_ID` | OAuth Client ID from IServ | Replit + Render |
| `ISERV_CLIENT_SECRET` | OAuth Client Secret from IServ | Replit + Render |
| `ISERV_DOMAIN` | `kgs-pattensen.de` | Replit + Render |

## E-Mail Service

E-Mails werden über **Resend** versendet.

**In Replit:** Automatisch über Replit Connector

**In Render:** Environment Variables setzen:
- `RESEND_API_KEY` - Resend API-Key (von resend.com)

Absender: `SportOase <onboarding@resend.dev>` (Resend Test-Adresse, keine Domain-Verifizierung nötig)

## Deployment

Production deployment on Render.com:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 main:app`
- Database: PostgreSQL (internal)

## Support

- **E-Mail**: morelli.maurizio@kgs-pattensen.de
- **Telefon**: 0151 40349764
