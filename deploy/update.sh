#!/bin/bash
# ============================================================
#  Buchungssystem – Update auf dem VPS
#  Ausführen als root: bash /opt/buchungssystem/deploy/update.sh
# ============================================================
set -e

APP_DIR="/opt/buchungssystem"
SERVICE="buchungssystem"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔ $1${NC}"; }
step() { echo -e "\n${YELLOW}▶ $1${NC}"; }
err()  { echo -e "${RED}✘ $1${NC}"; exit 1; }

[[ $EUID -ne 0 ]] && err "Bitte als root ausführen"

cd "$APP_DIR"

step "Code aktualisieren (git pull)"
git pull
ok "Code aktuell"

step "Python-Pakete aktualisieren"
venv/bin/pip install --quiet -r requirements.txt
ok "Pakete aktuell"

step "Service neu starten"
systemctl restart "$SERVICE"
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
    ok "Service läuft"
else
    err "Service startet nicht – prüfe: journalctl -u $SERVICE -n 30"
fi

echo ""
echo -e "${GREEN}✔ Update abgeschlossen${NC}"
echo "  Logs: journalctl -u $SERVICE -f"
