#!/bin/bash
# ============================================================
#  Buchungssystem – VPS Erstinstallation
#  Ausführen als root: bash install.sh
# ============================================================
set -e

APP_DIR="/opt/buchungssystem"
SERVICE="buchungssystem"
DOMAIN="igsbadenstedt.learngrid.app"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
err()  { echo -e "${RED}✘ $1${NC}"; exit 1; }
step() { echo -e "\n${YELLOW}▶ $1${NC}"; }

[[ $EUID -ne 0 ]] && err "Bitte als root ausführen (sudo bash install.sh)"

# ── 1. Pakete ────────────────────────────────────────────────
step "Systempakete installieren"
apt-get update -qq
apt-get install -y -qq nginx python3 python3-venv python3-pip git certbot python3-certbot-nginx
ok "Pakete installiert"

# ── 2. App-Verzeichnis & Code ────────────────────────────────
step "App-Verzeichnis vorbereiten"
mkdir -p "$APP_DIR/static/uploads" "$APP_DIR/logs"

if [ -d "$APP_DIR/.git" ]; then
    warn "Repo existiert bereits – führe git pull aus"
    cd "$APP_DIR" && git pull
else
    read -rp "  Git-Repository-URL (Enter für manuellen Upload): " REPO_URL
    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" "$APP_DIR"
    else
        warn "Kein Repo angegeben – Code muss manuell nach $APP_DIR kopiert werden"
        warn "Danach dieses Skript erneut ausführen"
        exit 0
    fi
fi
ok "Code bereit in $APP_DIR"

# ── 3. Python-Umgebung ───────────────────────────────────────
step "Python virtualenv einrichten"
cd "$APP_DIR"
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
ok "Python-Pakete installiert"

# ── 4. Umgebungsvariablen ────────────────────────────────────
step "Umgebungsvariablen konfigurieren"
if [ -f "$APP_DIR/.env" ]; then
    warn ".env existiert bereits – wird NICHT überschrieben"
else
    read -rp "  DATABASE_URL (postgresql://user:pass@host/db): " DB_URL
    [[ -z "$DB_URL" ]] && err "DATABASE_URL darf nicht leer sein"
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "$APP_DIR/.env" << EOF
DATABASE_URL=${DB_URL}
SESSION_SECRET=${SECRET}
EOF
    chmod 600 "$APP_DIR/.env"
    ok ".env erstellt (SESSION_SECRET automatisch generiert)"
fi

# ── 5. Berechtigungen ────────────────────────────────────────
chown -R www-data:www-data "$APP_DIR"
ok "Berechtigungen gesetzt"

# ── 6. Systemd-Service ───────────────────────────────────────
step "Systemd-Service einrichten"
cp "$APP_DIR/deploy/buchungssystem.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
    ok "Service läuft"
else
    err "Service startet nicht – prüfe: journalctl -u $SERVICE -n 30"
fi

# ── 7. nginx ────────────────────────────────────────────────
step "nginx konfigurieren"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/"$SERVICE"
ln -sf /etc/nginx/sites-available/"$SERVICE" /etc/nginx/sites-enabled/"$SERVICE"
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "nginx konfiguriert"

# ── 8. SSL-Zertifikat ────────────────────────────────────────
step "SSL-Zertifikat (Let's Encrypt)"
if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    warn "Zertifikat existiert bereits – wird erneuert"
    certbot renew --quiet
else
    read -rp "  E-Mail für Let's Encrypt: " LE_EMAIL
    [[ -z "$LE_EMAIL" ]] && err "E-Mail erforderlich für Let's Encrypt"
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$LE_EMAIL"
fi
ok "SSL-Zertifikat aktiv"

systemctl reload nginx

# ── Fertig ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Installation abgeschlossen!                 ║${NC}"
echo -e "${GREEN}║  https://${DOMAIN}  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "Nützliche Befehle:"
echo "  Logs live:     journalctl -u $SERVICE -f"
echo "  Status:        systemctl status $SERVICE"
echo "  Neustart:      systemctl restart $SERVICE"
echo "  Update:        bash $APP_DIR/deploy/update.sh"
