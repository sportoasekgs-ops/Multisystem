# LearnGrid – VPS Tutorial

Dieses Tutorial erklärt alles, was du auf dem Server tun musst: von der ersten
Code-Übertragung bis zum Hinzufügen einer neuen Schule. Jeder Schritt hat genau
die Befehle, die du eingeben musst.

---

## Teil 1 – Erstinstallation (einmalig)

### Schritt 1: Per SSH auf den VPS verbinden

Öffne ein Terminal (Windows: PowerShell oder PuTTY) und verbinde dich:

```bash
ssh root@87.106.155.5
```

Du solltest jetzt einen Prompt wie `root@vps:~#` sehen.

---

### Schritt 2: Code auf den VPS übertragen

Wähle **eine** der folgenden Methoden:

---

**Option A – Git (empfohlen, wenn du ein GitHub-Repo hast)**

```bash
# Auf dem VPS:
apt-get install -y git
git clone https://github.com/DEIN_USER/DEIN_REPO /opt/buchungssystem
```

Für private Repos brauchst du einen GitHub-Token:
```bash
git clone https://DEIN_TOKEN@github.com/DEIN_USER/DEIN_REPO /opt/buchungssystem
```

---

**Option B – rsync vom eigenen Rechner (kein GitHub nötig)**

Diesen Befehl auf deinem **lokalen Rechner** (nicht auf dem VPS) ausführen:

```bash
# Von deinem PC / Replit-Terminal aus:
rsync -avz \
  --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='venv/' --exclude='.pythonlibs/' --exclude='.env' \
  /pfad/zum/projekt/ root@87.106.155.5:/opt/buchungssystem/
```

Oder das fertige Push-Skript nutzen (konfiguriert sich selbst):
```bash
bash deploy/push_to_vps.sh
```

---

**Option C – Zip-Datei hochladen**

```bash
# Auf deinem PC: Projekt als ZIP herunterladen, dann hochladen:
scp learngrid.zip root@87.106.155.5:/tmp/

# Auf dem VPS:
mkdir -p /opt/buchungssystem
cd /opt/buchungssystem
unzip /tmp/learngrid.zip
```

---

### Schritt 3: Installationsskript ausführen

```bash
# Auf dem VPS (als root):
bash /opt/buchungssystem/deploy/install.sh
```

Das Skript fragt dich nach:
- Einer **Datenbank-URL** – wenn du PostgreSQL lokal installierst, lautet sie:
  `postgresql://learngrid:PASSWORT@localhost:5432/learngrid`
- Einer **E-Mail-Adresse** für das HTTPS-Zertifikat (Let's Encrypt)

Es erledigt dann automatisch:
- Python-Pakete installieren
- systemd-Service einrichten (startet automatisch beim Boot)
- nginx konfigurieren
- SSL-Zertifikat holen

Wenn alles klappt, siehst du am Ende:
```
╔══════════════════════════════════════════════╗
║  Installation abgeschlossen!                 ║
╚══════════════════════════════════════════════╝
```

---

### Schritt 4: Im Browser öffnen

Öffne `https://DEINE-DOMAIN.learngrid.app` — der Einrichtungs-Assistent
startet automatisch und führt dich durch die Schulkonfiguration.

---

---

## Teil 2 – Neue Schule hinzufügen

Für jede neue Schule läufst du genau **ein Skript** auf dem VPS.
Es erstellt automatisch: Datenbank, App-Instanz, nginx-Konfiguration und HTTPS.

### Schritt 1: Auf den VPS verbinden

```bash
ssh root@87.106.155.5
```

### Schritt 2: Provisionierungsskript starten

```bash
bash /opt/buchungssystem/deploy/provision_school.sh "KGS Pattensen"
```

Ersetze `"KGS Pattensen"` durch den echten Schulnamen. Der Subdomain-Name
wird automatisch abgeleitet (Sonderzeichen → Leerzeichen → Bindestriche):

| Schulname | → Subdomain |
|---|---|
| `KGS Pattensen` | `kgs-pattensen.learngrid.app` |
| `IGS Badenstedt` | `igs-badenstedt.learngrid.app` |
| `Grundschule Ost` | `grundschule-ost.learngrid.app` |

**Eigenen Subdomain-Namen festlegen** (optionaler 2. Parameter):
```bash
bash /opt/buchungssystem/deploy/provision_school.sh "KGS Pattensen" kgsp
# → https://kgsp.learngrid.app
```

### Schritt 3: DNS-Eintrag setzen (einziger manueller Schritt)

Das Skript pausiert und zeigt dir exakt, was du bei deinem DNS-Anbieter
(IONOS, Strato, Cloudflare, …) eintragen musst:

```
┌──────────────────────────────────────────────────────┐
│  Bitte bei deinem DNS-Anbieter setzen:               │
├──────────────────────────────────────────────────────┤
│  Typ:   A                                            │
│  Host:  kgs-pattensen                               │
│  Wert:  87.106.155.5                                │
│  TTL:   3600                                         │
└──────────────────────────────────────────────────────┘
```

**Bei IONOS:**
1. Mein IONOS → Domains & SSL → Domain anklicken
2. DNS → Eintrag hinzufügen
3. Typ `A`, Host = der angezeigte Name, Wert = die IP

Sobald gespeichert: **Enter drücken**. Das Skript wartet automatisch
bis zu 10 Minuten auf die DNS-Verbreitung und holt dann das HTTPS-Zertifikat.

### Schritt 4: Fertig

```
╔══════════════════════════════════════════╗
║  Schule erfolgreich eingerichtet!        ║
╠══════════════════════════════════════════╣
║  URL:   https://kgs-pattensen.learngrid.app
║  Port:  8002
║  DB:    learngrid_kgs_pattensen
╚══════════════════════════════════════════╝
  Beim ersten Aufruf startet der Einrichtungs-Assistent automatisch.
```

Öffne die angezeigte URL — der Assistent führt durch den Rest
(Schulname, Logo, Farben, IServ-OAuth, E-Mail-Einstellungen).

---

---

## Teil 3 – Updates einspielen

### Von deinem Entwicklungsrechner / Replit (einfachste Methode)

Einmalig konfigurieren (fragt die VPS-Adresse ab und speichert sie):
```bash
bash deploy/push_to_vps.sh
```

Danach reicht immer:
```bash
bash deploy/push_to_vps.sh                   # alle Schulen aktualisieren
bash deploy/push_to_vps.sh kgs-pattensen     # nur eine bestimmte Schule
bash deploy/push_to_vps.sh --dry-run         # Vorschau ohne Änderungen
```

Was passiert:
1. Nur geänderte Dateien werden per rsync übertragen (schnell)
2. `.env`, Logos (`static/uploads/`) und Logs bleiben unberührt
3. Jede App-Instanz wird automatisch neu gestartet
4. Gesundheitscheck bestätigt, dass alles läuft

---

### Direkt auf dem VPS (wenn Code per Git kommt)

```bash
ssh root@87.106.155.5
bash /opt/buchungssystem/deploy/redeploy.sh
```

Varianten:
```bash
bash /opt/buchungssystem/deploy/redeploy.sh                  # git pull + alle Schulen
bash /opt/buchungssystem/deploy/redeploy.sh --no-pull        # ohne git pull
bash /opt/buchungssystem/deploy/redeploy.sh kgs-pattensen    # nur eine Schule
bash /opt/buchungssystem/deploy/redeploy.sh --status         # nur Status anzeigen
```

---

---

## Teil 4 – Verwaltung & Monitoring

### Alle Schulen auf einen Blick

```bash
bash /opt/buchungssystem/deploy/provision_school.sh --list
# oder:
bash /opt/buchungssystem/deploy/redeploy.sh --status
```

Ausgabe:
```
  kgs-pattensen     Port: 8001   active
  igs-badenstedt    Port: 8002   active
  grundschule-ost   Port: 8003   inactive  ← Problem!
```

### Eine einzelne Schule verwalten

```bash
# Status anzeigen
systemctl status learngrid@kgs-pattensen

# Live-Logs (Fehler einsehen)
journalctl -u learngrid@kgs-pattensen -f

# Neu starten
systemctl restart learngrid@kgs-pattensen

# Stoppen / Starten
systemctl stop  learngrid@kgs-pattensen
systemctl start learngrid@kgs-pattensen
```

### nginx-Konfigurationen prüfen

```bash
nginx -t                    # Konfiguration auf Fehler prüfen
systemctl reload nginx      # Konfiguration neu laden (ohne Unterbrechung)
systemctl status nginx      # nginx-Status
```

### Zertifikate erneuern

Zertifikate werden automatisch erneuert (certbot-Timer). Manuell:
```bash
certbot renew
systemctl reload nginx
```

---

---

## Teil 5 – Häufige Probleme & Lösungen

### „502 Bad Gateway" im Browser

Der Service läuft nicht. Lösung:
```bash
systemctl restart learngrid@SLUG
journalctl -u learngrid@SLUG -n 50    # Fehlerursache anzeigen
```

### App startet nicht nach Update

```bash
journalctl -u learngrid@SLUG -n 50 --no-pager
# Häufige Ursachen:
# - Syntaxfehler in geändertem Python-Code
# - Fehlende Python-Pakete (requirements.txt geändert?)
```

Pakete manuell aktualisieren:
```bash
/srv/learngrid/venv/bin/pip install -r /opt/buchungssystem/requirements.txt
systemctl restart learngrid@SLUG
```

### Datenbank-Verbindungsfehler

```bash
cat /srv/learngrid/SLUG/.env          # DATABASE_URL prüfen
sudo -u postgres psql -l              # Datenbanken anzeigen
```

### HTTPS-Zertifikat fehlt oder abgelaufen

```bash
certbot --nginx -d SLUG.learngrid.app \
    --non-interactive --agree-tos -m deine@email.de --redirect
systemctl reload nginx
```

### DNS zeigt noch nicht auf den VPS

```bash
# DNS-Auflösung testen (von überall):
dig +short A kgs-pattensen.learngrid.app @1.1.1.1

# Sollte die VPS-IP zurückgeben. Falls nicht: noch warten oder
# A-Record bei deinem DNS-Anbieter nochmal prüfen.
```

---

---

## Übersicht: Wo liegt was auf dem VPS?

```
/opt/buchungssystem/           ← Quellcode (dein Repo / rsync-Ziel)
├── app.py, models.py, ...
├── requirements.txt
└── deploy/
    ├── provision_school.sh    ← Neue Schule anlegen
    ├── redeploy.sh            ← Auf dem VPS patchen
    ├── push_to_vps.sh         ← Von lokal pushen
    ├── install.sh             ← Erstinstallation
    └── SETUP_VPS.md           ← Dieses Tutorial

/srv/learngrid/
├── venv/                      ← Gemeinsame Python-Umgebung (alle Schulen)
├── kgs-pattensen/             ← Instanz Schule 1
│   ├── .env                   ← Datenbank-URL + Session-Secret (geheim!)
│   ├── buchungssystem_local.json   ← vom Setup-Assistent erstellt
│   ├── static/uploads/        ← Logos & Favicons (bleiben beim Update erhalten)
│   └── logs/                  ← access.log, error.log
├── igs-badenstedt/            ← Instanz Schule 2
└── ...

/etc/learngrid/provision.conf  ← Domain, VPS-IP, E-Mail (einmalig gespeichert)
/etc/nginx/sites-available/    ← nginx-Konfigurationen
/etc/systemd/system/learngrid@.service   ← systemd-Template für alle Schulen
```

---

## Schnellreferenz

| Aufgabe | Befehl |
|---|---|
| Neue Schule anlegen | `bash /opt/buchungssystem/deploy/provision_school.sh "Schulname"` |
| Alle Schulen anzeigen | `bash /opt/buchungssystem/deploy/provision_school.sh --list` |
| Von lokal pushen + neu starten | `bash deploy/push_to_vps.sh` |
| Auf VPS alle Schulen neu starten | `bash /opt/buchungssystem/deploy/redeploy.sh` |
| Status prüfen | `bash /opt/buchungssystem/deploy/redeploy.sh --status` |
| Eine Schule neu starten | `systemctl restart learngrid@SLUG` |
| Logs anzeigen | `journalctl -u learngrid@SLUG -f` |
