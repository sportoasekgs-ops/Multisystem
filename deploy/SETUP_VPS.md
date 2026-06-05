# LearnGrid – VPS Deployment Guide

**Server:** Ubuntu 22.04 / 24.04  
**Struktur:** Jede Schule bekommt eigene DB, App-Instanz, Subdomain und HTTPS-Zertifikat.

---

## Schnellreferenz

| Aufgabe | Befehl |
|---|---|
| Neue Schule anlegen | `bash deploy/provision_school.sh "IGS Badenstedt"` |
| Code pushen + alle Schulen neu starten | `bash deploy/push_to_vps.sh` |
| Nur eine Schule patchen | `bash deploy/push_to_vps.sh igs-badenstedt` |
| Alle Schulen auf VPS neu starten | `ssh root@VPS "bash /opt/learngrid/deploy/redeploy.sh"` |
| Status aller Instanzen | `ssh root@VPS "bash /opt/learngrid/deploy/redeploy.sh --status"` |

---

## Erstinstallation (einmalig pro VPS)

### 1. Code auf den VPS bringen

**Option A: Git (empfohlen)**
```bash
ssh root@DEIN_VPS_IP
git clone https://github.com/DEIN_USER/DEIN_REPO /opt/learngrid
```

**Option B: Direkt per rsync vom Entwicklungsrechner**
```bash
bash deploy/push_to_vps.sh   # (konfiguriert sich beim ersten Aufruf selbst)
```

### 2. Installationsskript ausführen
```bash
ssh root@DEIN_VPS_IP
bash /opt/learngrid/deploy/install.sh
```
Richtet nginx, PostgreSQL, systemd und das erste SSL-Zertifikat ein.

---

## Neue Schule hinzufügen

```bash
ssh root@DEIN_VPS_IP
bash /opt/learngrid/deploy/provision_school.sh "IGS Badenstedt"
```

**Was das Skript automatisch erledigt:**
1. PostgreSQL-Datenbank + eigenen DB-User anlegen
2. Isoliertes App-Verzeichnis unter `/srv/learngrid/<slug>/` erstellen
3. Freien Port zuweisen und `.env` mit DB-URL + Session-Secret schreiben
4. systemd-Service `learngrid@<slug>` einrichten und starten
5. nginx-vhost für `<slug>.learngrid.app` anlegen
6. Let's-Encrypt-Zertifikat holen (nach DNS-Verbreitung)

**Einziger manueller Schritt:** Das Skript zeigt dir genau, welchen A-Record
du bei deinem DNS-Anbieter setzen musst, und wartet automatisch auf die Verbreitung.

Nach dem Skript öffnet der Einrichtungs-Assistent bei `https://<slug>.learngrid.app`
und führt durch die Schulkonfiguration (Name, Branding, IServ-OAuth, E-Mail, etc.).

**Optionaler eigener Slug (Subdomain-Name):**
```bash
bash deploy/provision_school.sh "IGS Badenstedt" igs-bs
# → https://igs-bs.learngrid.app
```

**Alle Instanzen anzeigen:**
```bash
bash /opt/learngrid/deploy/provision_school.sh --list
```

---

## Updates / Patches einspielen

### Von deinem Entwicklungsrechner oder Replit (empfohlen)

```bash
# Einmalig konfigurieren (wird in deploy/.push_config gespeichert):
bash deploy/push_to_vps.sh
# → fragt VPS-Adresse ab und speichert sie

# Ab dann einfach:
bash deploy/push_to_vps.sh                  # alle Schulen
bash deploy/push_to_vps.sh igs-badenstedt   # nur eine Schule
bash deploy/push_to_vps.sh --dry-run        # Vorschau ohne Änderungen
```

Was passiert:
- rsync überträgt nur geänderte Dateien (`.env`, `static/uploads`, Logs bleiben unangetastet)
- Ruft auf dem VPS `redeploy.sh --no-pull` auf
- Jede Instanz wird kurz neu gestartet, Gesundheitscheck folgt

### Direkt auf dem VPS (z.B. via Git-Workflow)

```bash
ssh root@DEIN_VPS_IP
bash /opt/learngrid/deploy/redeploy.sh              # git pull + alle Schulen
bash /opt/learngrid/deploy/redeploy.sh --no-pull    # ohne git pull
bash /opt/learngrid/deploy/redeploy.sh igs-bs       # nur eine Schule
bash /opt/learngrid/deploy/redeploy.sh --status     # nur Status anzeigen
```

---

## Verwaltung einzelner Schulen

```bash
# Status
systemctl status learngrid@igs-badenstedt

# Live-Logs
journalctl -u learngrid@igs-badenstedt -f

# Neustart
systemctl restart learngrid@igs-badenstedt

# Stoppen / Starten
systemctl stop learngrid@igs-badenstedt
systemctl start learngrid@igs-badenstedt
```

---

## Dateistruktur auf dem VPS

```
/opt/learngrid/                         ← Quellcode (git repo oder rsync-Ziel)
├── app.py, models.py, ...
├── requirements.txt
└── deploy/
    ├── provision_school.sh             ← Neue Schule anlegen
    ├── redeploy.sh                     ← Code + Neustart auf dem VPS
    ├── push_to_vps.sh                  ← Push vom Entwicklungsrechner
    ├── install.sh                      ← Erstinstallation
    └── SETUP_VPS.md                    ← Diese Anleitung

/srv/learngrid/
├── venv/                               ← Gemeinsame Python-Umgebung
├── igs-badenstedt/                     ← Instanz Schule 1
│   ├── .env                            ← DB-URL + Session-Secret (geheim!)
│   ├── buchungssystem_local.json       ← vom Setup-Wizard erstellt
│   ├── static/uploads/                 ← Logos, Favicons (nicht überschrieben)
│   └── logs/                           ← access.log, error.log
├── kgs-muster/                         ← Instanz Schule 2
│   └── ...
└── ...

/etc/learngrid/provision.conf           ← Domain, IP, LE-E-Mail (einmalig gespeichert)
/etc/nginx/sites-available/learngrid-*  ← nginx-vhosts
/etc/systemd/system/learngrid@.service  ← systemd-Template
```

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| `502 Bad Gateway` | `systemctl restart learngrid@<slug>` |
| Service startet nicht | `journalctl -u learngrid@<slug> -n 50` |
| Datenbank-Fehler | `.env` in `/srv/learngrid/<slug>/` prüfen |
| Zertifikat abgelaufen | `certbot renew && systemctl reload nginx` |
| nginx-Fehler | `nginx -t` |
| SSH-Key fehlt | `ssh-copy-id root@VPS_IP` |
| Port belegt | `ss -tlnp \| grep PORT` |

---

## HTTPS nachträglich einrichten

Falls beim Provisionieren das DNS noch nicht aktiv war:
```bash
certbot --nginx -d <slug>.learngrid.app \
    --non-interactive --agree-tos \
    -m deine@email.de --redirect
systemctl reload nginx
```
