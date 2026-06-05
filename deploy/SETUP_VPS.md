# VPS Einrichtung – igsbadenstedt.learngrid.app

## Voraussetzungen
- Ubuntu 22.04 / Debian 12
- Root-Zugang
- Port 80 und 443 in der VPS-Firewall offen

## 1. Pakete installieren

```bash
apt update && apt install -y nginx python3 python3-venv python3-pip certbot python3-certbot-nginx
```

## 2. App deployen

```bash
mkdir -p /opt/buchungssystem
cd /opt/buchungssystem
git clone <dein-repo-url> .
python3 -m venv venv
venv/bin/pip install -r requirements.txt
mkdir -p static/uploads logs
```

## 3. Umgebungsvariablen setzen

```bash
cat > /opt/buchungssystem/.env << 'EOF'
SESSION_SECRET=<langer-zufaelliger-string>
EOF
```

Session-Secret generieren:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 4. Systemd-Service einrichten

```bash
cp deploy/buchungssystem.service /etc/systemd/system/
chown -R www-data:www-data /opt/buchungssystem
systemctl daemon-reload
systemctl enable buchungssystem
systemctl start buchungssystem
```

Status prüfen:
```bash
systemctl status buchungssystem
journalctl -u buchungssystem -f
```

## 5. Nginx konfigurieren (HTTP zuerst – für Certbot)

```bash
cp deploy/nginx.conf /etc/nginx/sites-available/buchungssystem
ln -s /etc/nginx/sites-available/buchungssystem /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## 6. SSL-Zertifikat holen (Let's Encrypt)

```bash
certbot --nginx -d igsbadenstedt.learngrid.app
```

Certbot ergänzt die nginx-Konfiguration automatisch. Danach:
```bash
systemctl reload nginx
```

## 7. HTTPS testen

```bash
curl -I https://igsbadenstedt.learngrid.app
```

Sollte `HTTP/2 200` oder `HTTP/1.1 302` zurückgeben.

## Fehlersuche HTTPS

### App läuft, aber HTTPS nicht erreichbar
```bash
# Firewall prüfen (ufw)
ufw status
ufw allow 80
ufw allow 443

# Oder iptables
iptables -L | grep -E "80|443"

# Nginx läuft?
systemctl status nginx

# App läuft auf Port 5000?
ss -tlnp | grep 5000
```

### Zertifikat erneuern (automatisch via Cron)
```bash
certbot renew --dry-run
```

## Updates einspielen

```bash
cd /opt/buchungssystem
git pull
venv/bin/pip install -r requirements.txt
systemctl restart buchungssystem
```
