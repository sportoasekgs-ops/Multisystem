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

## Updates einspielen

**Wenn Code per GitHub:**
```bash
ssh root@87.106.155.5
bash /opt/buchungssystem/deploy/update.sh
```

**Wenn Code per rsync:**
```bash
# Erst Code übertragen
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='buchungssystem_local.json' \
  /pfad/zum/projekt/ root@87.106.155.5:/opt/buchungssystem/

# Dann Service neustarten
ssh root@87.106.155.5 "systemctl restart buchungssystem"
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
