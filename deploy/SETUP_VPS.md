# VPS Deployment – Buchungssystem

**VPS:** 87.106.155.5 | Ubuntu 24.04  
**Domain:** igsbadenstedt.learngrid.app  
**Ports:** 80, 443 offen

---

## Erstinstallation (einmalig)

### Schritt 1 – Code auf den VPS übertragen

**Option A: Über GitHub (empfohlen)**  
Erst das Replit-Projekt mit GitHub verbinden (Replit → Version Control → Connect to GitHub), dann:
```bash
ssh root@87.106.155.5
git clone https://github.com/DEIN_USER/DEIN_REPO /opt/buchungssystem
```

**Option B: Direkt per rsync (von deinem PC aus)**
```bash
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  /pfad/zum/projekt/ root@87.106.155.5:/opt/buchungssystem/
```

**Option C: Zip herunterladen & hochladen**
```bash
# Zip auf VPS hochladen
scp buchungssystem.zip root@87.106.155.5:/tmp/
ssh root@87.106.155.5
mkdir -p /opt/buchungssystem
cd /opt/buchungssystem
unzip /tmp/buchungssystem.zip
```

---

### Schritt 2 – Installationsskript ausführen

```bash
ssh root@87.106.155.5
bash /opt/buchungssystem/deploy/install.sh
```

Das Skript erledigt alles automatisch:
- Python-Pakete installieren (venv)
- `.env` mit DATABASE_URL und SESSION_SECRET anlegen
- Systemd-Service einrichten und starten
- nginx konfigurieren
- SSL-Zertifikat (Let's Encrypt) holen

---

## Neue Schule hinzufügen (Multi-School)

Eine weitere Schule auf demselben VPS anlegen – Datenbank, Subdomain-Instanz,
nginx und HTTPS werden automatisch erzeugt:

```bash
ssh root@87.106.155.5
bash /opt/buchungssystem/deploy/provision_school.sh "IGS Badenstedt"
```

Das Skript:
- legt eine **eigene PostgreSQL-Datenbank** für die Schule an
- erstellt eine **isolierte App-Instanz** (eigenes Verzeichnis unter `/srv/learngrid/<slug>`, eigener Port, eigener systemd-Service `learngrid@<slug>`)
- richtet den **nginx-vhost** für `<slug>.learngrid.app` ein
- holt das **HTTPS-Zertifikat** (Let's Encrypt)

Beim ersten Lauf werden Basis-Domain, VPS-IP und Let's-Encrypt-E-Mail einmalig
abgefragt und in `/etc/learngrid/provision.conf` gespeichert.

**Einziger manueller Schritt:** Wenn das Skript dazu auffordert, bei IONOS einen
**A-Record** anlegen (`<slug>` → VPS-IP). Das Skript wartet automatisch, bis der
Eintrag aktiv ist, und holt dann das Zertifikat. Danach ist
`https://<slug>.learngrid.app` aufrufbar und der Einrichtungs-Assistent führt
durch den Rest.

Optional lässt sich der Subdomain-Name (Slug) als 2. Parameter überschreiben:
```bash
bash deploy/provision_school.sh "IGS Badenstedt" igs-bs
```

Verwaltung einer Schul-Instanz:
```bash
systemctl status learngrid@igs-badenstedt
journalctl -u learngrid@igs-badenstedt -f
systemctl restart learngrid@igs-badenstedt
```

---

## Updates einspielen (Redeploy)

**Multi-School (empfohlen):** aktualisiert den Code in **allen** Schul-Instanzen
und startet sie neu. Pro Schule bleiben `.env`, `buchungssystem_local.json` und
`static/uploads` (Logos) unberührt.

```bash
ssh root@87.106.155.5
bash /opt/buchungssystem/deploy/redeploy.sh
```

Varianten:
```bash
bash deploy/redeploy.sh --no-pull        # ohne git pull (Code schon aktuell)
bash deploy/redeploy.sh igs-badenstedt   # nur eine bestimmte Schule
```

Wenn der Code per rsync statt git kommt, erst übertragen, dann `--no-pull`:
```bash
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='buchungssystem_local.json' \
  /pfad/zum/projekt/ root@87.106.155.5:/opt/buchungssystem/
ssh root@87.106.155.5 "bash /opt/buchungssystem/deploy/redeploy.sh --no-pull"
```

**Altes Einzel-Setup (nur eine Schule, ohne Multi-School):**
```bash
ssh root@87.106.155.5
bash /opt/buchungssystem/deploy/update.sh
```

---

## Nützliche Befehle auf dem VPS

```bash
# Live-Logs
journalctl -u buchungssystem -f

# Status
systemctl status buchungssystem

# Neustart
systemctl restart buchungssystem

# App läuft auf Port 5000?
ss -tlnp | grep 5000

# HTTPS testen
curl -I https://igsbadenstedt.learngrid.app
```

---

## Häufige Fehler

| Problem | Lösung |
|---|---|
| `502 Bad Gateway` | `systemctl restart buchungssystem` |
| App startet nicht | `journalctl -u buchungssystem -n 50` |
| DB-Verbindung schlägt fehl | DATABASE_URL in `/opt/buchungssystem/.env` prüfen |
| Zertifikat abgelaufen | `certbot renew && systemctl reload nginx` |
| nginx-Fehler | `nginx -t` zum Testen |

---

## Dateistruktur auf dem VPS

```
/opt/buchungssystem/
├── .env                        ← DATABASE_URL + SESSION_SECRET (geheim!)
├── buchungssystem_local.json   ← wird vom Setup-Wizard erstellt
├── venv/                       ← Python-Umgebung
├── static/uploads/             ← Logos, Favicons
└── deploy/
    ├── install.sh              ← Erstinstallation
    ├── update.sh               ← Updates
    ├── buchungssystem.service  ← Systemd-Unit
    └── nginx.conf              ← nginx-Konfiguration
```
