# VPS Einrichtung – igsbadenstedt.learngrid.app

**VPS:** 87.106.155.5 | Ubuntu 24.04  
**Firewall:** Port 80, 443 ✅ offen

---

## Schritt 1 – Als root auf dem VPS einloggen

```bash
ssh root@87.106.155.5
```

---

## Schritt 2 – Pakete installieren

```bash
apt update && apt install -y nginx python3 python3-venv python3-pip git certbot python3-certbot-nginx
```

---

## Schritt 3 – App-Verzeichnis anlegen und Code holen

```bash
mkdir -p /opt/buchungssystem
cd /opt/buchungssystem
git clone <DEIN_REPO_URL> .
python3 -m venv venv
venv/bin/pip install -r requirements.txt
mkdir -p static/uploads logs
chown -R www-data:www-data /opt/buchungssystem
```

---

## Schritt 4 – Umgebungsvariablen setzen

```bash
cat > /opt/buchungssystem/.env << 'EOF'
DATABASE_URL=postgresql://learngrid_user:DEIN_PASSWORT@localhost:5432/learngrid
SESSION_SECRET=HIER_LANGEN_ZUFAELLIGEN_STRING_EINFUEGEN
EOF

chmod 600 /opt/buchungssystem/.env
```

Session-Secret generieren (diesen Befehl ausführen und Ausgabe kopieren):
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Schritt 5 – Systemd-Service einrichten

```bash
cp /opt/buchungssystem/deploy/buchungssystem.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable buchungssystem
systemctl start buchungssystem
```

Status prüfen (sollte "active (running)" zeigen):
```bash
systemctl status buchungssystem
```

Logs live verfolgen:
```bash
journalctl -u buchungssystem -f
```

---

## Schritt 6 – nginx konfigurieren (erstmal nur HTTP für Certbot)

```bash
cp /opt/buchungssystem/deploy/nginx.conf /etc/nginx/sites-available/buchungssystem
ln -s /etc/nginx/sites-available/buchungssystem /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

---

## Schritt 7 – SSL-Zertifikat holen (Let's Encrypt)

```bash
certbot --nginx -d igsbadenstedt.learngrid.app
```

Certbot fragt nach einer E-Mail-Adresse und ergänzt die nginx-Konfiguration automatisch. Danach:

```bash
systemctl reload nginx
```

---

## Schritt 8 – Testen

```bash
# App läuft auf Port 5000?
ss -tlnp | grep 5000

# nginx hört auf 443?
ss -tlnp | grep 443

# HTTPS-Antwort testen
curl -I https://igsbadenstedt.learngrid.app
```

Erwartete Antwort: `HTTP/2 200` oder `HTTP/1.1 302 FOUND`

---

## Updates einspielen

```bash
cd /opt/buchungssystem
git pull
venv/bin/pip install -r requirements.txt
systemctl restart buchungssystem
```

---

## Häufige Fehler

| Problem | Lösung |
|---|---|
| `502 Bad Gateway` | App läuft nicht: `systemctl start buchungssystem` |
| `curl: (7) Failed to connect` | nginx läuft nicht: `systemctl start nginx` |
| Zertifikat-Fehler | `certbot renew` |
| App startet nicht | `journalctl -u buchungssystem -n 50` prüfen |
| DB-Verbindung schlägt fehl | PostgreSQL-User-Rechte prüfen: `psql -U postgres -c "\du"` |
