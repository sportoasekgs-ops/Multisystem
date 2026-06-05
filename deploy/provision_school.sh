#!/bin/bash
# ============================================================
#  LearnGrid – Neue Schule automatisch anlegen
#  ----------------------------------------------------------
#  Aufruf (als root auf dem VPS):
#
#    bash provision_school.sh "IGS Badenstedt"
#    bash provision_school.sh "IGS Badenstedt" igs-bs   # eigener Slug
#    bash provision_school.sh --list                     # alle Instanzen anzeigen
#
#  Legt vollautomatisch an:
#    1. Eigene PostgreSQL-Datenbank
#    2. Isolierte App-Instanz (Verzeichnis + Port + systemd-Service)
#    3. nginx-vhost fuer die Subdomain
#    4. HTTPS-Zertifikat (Let's Encrypt)
#
#  Einziger manueller Schritt: A-Record bei deinem DNS-Anbieter setzen.
#  Das Skript sagt dir was einzutragen ist und wartet automatisch.
# ============================================================
set -euo pipefail

# ── Konfiguration ───────────────────────────────────────────
# SRC_DIR: automatisch suchen wenn nicht explizit gesetzt
if [[ -z "${SRC_DIR:-}" ]]; then
    for _candidate in \
        "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)" \
        /opt/learngrid \
        /opt/buchungssystem \
        /opt/slotra \
        /var/www/learngrid; do
        if [[ -f "$_candidate/main.py" ]]; then
            SRC_DIR="$_candidate"
            break
        fi
    done
fi
SRC_DIR="${SRC_DIR:-/opt/learngrid}"
BASE_ROOT="/srv/learngrid"
SHARED_VENV="$BASE_ROOT/venv"
CONF_FILE="/etc/learngrid/provision.conf"
PORT_START=8001

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()    { echo -e "${GREEN}✔ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $*${NC}"; }
err()   { echo -e "${RED}✘ $*${NC}"; exit 1; }
step()  { echo -e "\n${BLUE}▶ $*${NC}"; }
info()  { echo -e "${CYAN}  $*${NC}"; }

[[ $EUID -ne 0 ]] && err "Bitte als root ausfuehren:  sudo bash provision_school.sh \"Schulname\""

# ── --list: alle Instanzen anzeigen ─────────────────────────
if [[ "${1:-}" == "--list" ]]; then
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  LearnGrid – Aktive Schulinstanzen                          ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    FOUND=0
    if [[ -d "$BASE_ROOT" ]]; then
        for d in "$BASE_ROOT"/*/; do
            slug="$(basename "$d")"
            [[ "$slug" == "venv" ]] && continue
            [[ -f "$d/.env" ]] || continue
            FOUND=$((FOUND+1))
            PORT="$(grep '^PORT=' "$d/.env" 2>/dev/null | cut -d= -f2)"
            STATUS="$(systemctl is-active "learngrid@${slug}" 2>/dev/null || echo "inaktiv")"
            [[ "$STATUS" == "active" ]] && COL="$GREEN" || COL="$RED"
            echo -e "  ${BLUE}${slug}${NC}  Port: ${PORT:-?}  Status: ${COL}${STATUS}${NC}"
        done
    fi
    [[ "$FOUND" == "0" ]] && warn "Keine Instanzen gefunden unter $BASE_ROOT"
    echo ""
    exit 0
fi

SCHOOL_NAME="${1:-}"
[[ -z "$SCHOOL_NAME" ]] && err "Bitte den Schulnamen angeben:  bash provision_school.sh \"IGS Badenstedt\""

# ── Lock gegen parallele Laeufe ─────────────────────────────
LOCK_FILE="/var/lock/learngrid-provision.lock"
exec 200>"$LOCK_FILE"
flock -n 200 || err "Eine andere Provisionierung laeuft gerade. Bitte warten."

# ── Rollback bei Fehler ─────────────────────────────────────
SUCCESS=0
CREATED_DB=0; CREATED_DIR=0; CREATED_UNIT=0; CREATED_NGINX=0
cleanup() {
    [[ "$SUCCESS" == "1" ]] && return
    echo ""
    warn "Fehler erkannt – mache angelegte Ressourcen rueckgaengig ..."
    if [[ "$CREATED_NGINX" == "1" ]]; then
        rm -f "/etc/nginx/sites-enabled/learngrid-${SLUG}" \
               "/etc/nginx/sites-available/learngrid-${SLUG}"
        nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
    fi
    if [[ "$CREATED_UNIT" == "1" ]]; then
        systemctl disable --now "learngrid@${SLUG}" >/dev/null 2>&1 || true
    fi
    [[ "$CREATED_DIR" == "1" ]] && rm -rf "$INSTANCE_DIR"
    if [[ "$CREATED_DB" == "1" ]]; then
        sudo -u postgres psql >/dev/null 2>&1 <<SQL || true
DROP DATABASE IF EXISTS "$DB_NAME";
DROP USER IF EXISTS "$DB_USER";
SQL
    fi
    warn "Aufgeraeumt. Du kannst das Skript erneut ausfuehren."
}
trap cleanup EXIT

# ── Gespeicherte Einstellungen laden / einmalig abfragen ────
mkdir -p "$(dirname "$CONF_FILE")"
[[ -f "$CONF_FILE" ]] && source "$CONF_FILE"

BASE_DOMAIN="${BASE_DOMAIN:-}"
VPS_IP="${VPS_IP:-}"
LE_EMAIL="${LE_EMAIL:-}"

if [[ -z "$BASE_DOMAIN" ]]; then
    read -rp "  Basis-Domain (z.B. learngrid.app): " BASE_DOMAIN
    [[ -z "$BASE_DOMAIN" ]] && err "Basis-Domain erforderlich"
fi
if [[ -z "$VPS_IP" ]]; then
    DETECTED_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    read -rp "  Oeffentliche IP dieses VPS [${DETECTED_IP}]: " VPS_IP
    VPS_IP="${VPS_IP:-$DETECTED_IP}"
    [[ -z "$VPS_IP" ]] && err "VPS-IP erforderlich"
fi
if [[ -z "$LE_EMAIL" ]]; then
    read -rp "  E-Mail fuer Let's Encrypt: " LE_EMAIL
    [[ -z "$LE_EMAIL" ]] && err "E-Mail fuer Let's Encrypt erforderlich"
fi

cat > "$CONF_FILE" <<EOF
BASE_DOMAIN="$BASE_DOMAIN"
VPS_IP="$VPS_IP"
LE_EMAIL="$LE_EMAIL"
EOF
chmod 600 "$CONF_FILE"

# ── Slug aus Schulname ableiten ──────────────────────────────
SLUG="$(printf '%s' "$SCHOOL_NAME" \
    | sed -e 's/\xc3\x84/Ae/g; s/\xc3\x96/Oe/g; s/\xc3\x9c/Ue/g; \
               s/\xc3\xa4/ae/g; s/\xc3\xb6/oe/g; s/\xc3\xbc/ue/g; \
               s/\xc3\x9f/ss/g' \
    | tr '[:upper:]' '[:lower:]' \
    | sed -e 's/[^a-z0-9]\+/-/g; s/^-\+//; s/-\+$//')"
[[ -n "${2:-}" ]] && SLUG="$2"
[[ -z "$SLUG" ]] && err "Konnte aus dem Schulnamen keinen gueltigen Slug ableiten"

if ! [[ "$SLUG" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
    err "Ungueltiger Slug '$SLUG' (erlaubt: a-z, 0-9, Bindestrich; nicht am Anfang/Ende)"
fi

FQDN="${SLUG}.${BASE_DOMAIN}"
INSTANCE_DIR="$BASE_ROOT/$SLUG"
DB_NAME="learngrid_$(echo "$SLUG" | tr '-' '_')"
DB_USER="$DB_NAME"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Neue Schule anlegen                     ║${NC}"
echo -e "${BLUE}╠══════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  Name:       ${SCHOOL_NAME}"
echo -e "${BLUE}║${NC}  Adresse:    https://${FQDN}"
echo -e "${BLUE}║${NC}  Datenbank:  ${DB_NAME}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

[[ -d "$INSTANCE_DIR" ]] && err "Instanz '$SLUG' existiert bereits ($INSTANCE_DIR)"
[[ -d "$SRC_DIR" ]]       || err "Quellcode nicht gefunden in $SRC_DIR (SRC_DIR= anpassen)"

# ── 0. Pakete sicherstellen ──────────────────────────────────
step "Systempakete pruefen"
NEED_PKGS=()
command -v nginx    >/dev/null || NEED_PKGS+=(nginx)
command -v psql     >/dev/null || NEED_PKGS+=(postgresql postgresql-client)
command -v certbot  >/dev/null || NEED_PKGS+=(certbot python3-certbot-nginx)
command -v rsync    >/dev/null || NEED_PKGS+=(rsync)
command -v dig      >/dev/null || NEED_PKGS+=(dnsutils)
python3 -m venv --help >/dev/null 2>&1 || NEED_PKGS+=(python3-venv python3-dev)
if [[ ${#NEED_PKGS[@]} -gt 0 ]]; then
    warn "Installiere: ${NEED_PKGS[*]}"
    apt-get update -qq && apt-get install -y -qq "${NEED_PKGS[@]}"
fi
systemctl enable --now postgresql >/dev/null 2>&1 || true
ok "Pakete bereit"

# ── 1. PostgreSQL-Datenbank anlegen ─────────────────────────
step "Datenbank anlegen: $DB_NAME"
DB_PASS="$(openssl rand -hex 24)"
DB_EXISTS="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" 2>/dev/null)"
[[ "$DB_EXISTS" == "1" ]] && err "Datenbank $DB_NAME existiert bereits"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE USER "${DB_USER}" WITH PASSWORD '${DB_PASS}';
CREATE DATABASE "${DB_NAME}" OWNER "${DB_USER}";
GRANT ALL PRIVILEGES ON DATABASE "${DB_NAME}" TO "${DB_USER}";
SQL
CREATED_DB=1
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
ok "Datenbank und Benutzer angelegt"

# ── 2. Instanz-Verzeichnis ───────────────────────────────────
step "App-Instanz einrichten"
mkdir -p "$INSTANCE_DIR"
CREATED_DIR=1
rsync -a \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='venv' --exclude='.venv' --exclude='node_modules' \
    --exclude='.env' --exclude='buchungssystem_local.json' \
    --exclude='scratch' --exclude='logs' --exclude='deploy' \
    "$SRC_DIR"/ "$INSTANCE_DIR"/
mkdir -p "$INSTANCE_DIR/static/uploads" "$INSTANCE_DIR/logs"
ok "Code nach $INSTANCE_DIR kopiert"

# ── 3. Python-Umgebung (einmalig, geteilt) ──────────────────
step "Python-Umgebung pruefen"
if [[ ! -x "$SHARED_VENV/bin/gunicorn" ]]; then
    warn "Erstelle gemeinsame Python-Umgebung in $SHARED_VENV (einmalig, dauert kurz)..."
    python3 -m venv "$SHARED_VENV"
    "$SHARED_VENV/bin/pip" install --quiet --upgrade pip
    "$SHARED_VENV/bin/pip" install --quiet -r "$INSTANCE_DIR/requirements.txt"
    ok "Python-Umgebung erstellt"
else
    ok "Python-Umgebung bereits vorhanden"
fi

# ── 4. Freien Port waehlen ──────────────────────────────────
step "Port zuweisen"
PORT=$PORT_START
while true; do
    USED="$(grep -rhoE '^PORT=[0-9]+$' "$BASE_ROOT"/*/.env 2>/dev/null | cut -d= -f2 || true)"
    echo "$USED" | grep -qx "$PORT" && { PORT=$((PORT+1)); continue; }
    ss -tlnH "sport = :$PORT" 2>/dev/null | grep -q . && { PORT=$((PORT+1)); continue; }
    break
done
ok "Port $PORT vergeben"

# ── 5. Konfigurationsdatei ──────────────────────────────────
SESSION_SECRET="$(openssl rand -hex 32)"
cat > "$INSTANCE_DIR/.env" <<EOF
DATABASE_URL=${DATABASE_URL}
SESSION_SECRET=${SESSION_SECRET}
PORT=${PORT}
FLASK_ENV=production
EOF
chmod 600 "$INSTANCE_DIR/.env"
chown -R www-data:www-data "$INSTANCE_DIR"
ok "Konfiguration erstellt (.env)"

# ── 6. systemd Template-Service ─────────────────────────────
step "systemd-Service einrichten"
TEMPLATE_UNIT="/etc/systemd/system/learngrid@.service"
if [[ ! -f "$TEMPLATE_UNIT" ]]; then
    cat > "$TEMPLATE_UNIT" <<UNIT
[Unit]
Description=LearnGrid Instanz %i
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=${BASE_ROOT}/%i
EnvironmentFile=${BASE_ROOT}/%i/.env
ExecStart=${SHARED_VENV}/bin/gunicorn \\
    --bind 127.0.0.1:\${PORT} \\
    --workers 3 \\
    --timeout 120 \\
    --access-logfile ${BASE_ROOT}/%i/logs/access.log \\
    --error-logfile ${BASE_ROOT}/%i/logs/error.log \\
    main:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    ok "systemd-Template erstellt"
else
    ok "systemd-Template bereits vorhanden"
fi
systemctl enable --now "learngrid@${SLUG}"
CREATED_UNIT=1
sleep 3
if systemctl is-active --quiet "learngrid@${SLUG}"; then
    ok "Service learngrid@${SLUG} laeuft auf Port $PORT"
else
    warn "Service startet nicht. Log:"
    journalctl -u "learngrid@${SLUG}" -n 20 --no-pager || true
    err "Service fehlgeschlagen. Oben stehende Logs pruefen."
fi

# ── 7. nginx-vhost anlegen ───────────────────────────────────
step "nginx konfigurieren"
NGINX_SITE="/etc/nginx/sites-available/learngrid-${SLUG}"
mkdir -p /var/www/html
cat > "$NGINX_SITE" <<NGINX
# LearnGrid – ${SCHOOL_NAME}
# Angelegt: $(date '+%Y-%m-%d %H:%M')
server {
    listen 80;
    listen [::]:80;
    server_name ${FQDN};

    # Let's Encrypt Challenge
    location /.well-known/acme-challenge/ { root /var/www/html; }

    # Statische Dateien direkt aus dem Dateisystem
    location /static/ {
        alias ${INSTANCE_DIR}/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # App-Proxy
    location / {
        proxy_pass         http://127.0.0.1:${PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
        client_max_body_size 16M;
    }
}
NGINX
ln -sf "$NGINX_SITE" "/etc/nginx/sites-enabled/learngrid-${SLUG}"
CREATED_NGINX=1
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "nginx-vhost fuer $FQDN aktiv (HTTP)"

# ── 8. DNS-Eintrag abwarten ─────────────────────────────────
step "DNS-Eintrag (einziger manueller Schritt)"
echo ""
echo -e "${YELLOW}  ┌─────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}  │  Bitte bei deinem DNS-Anbieter (z.B. IONOS) setzen: │${NC}"
echo -e "${YELLOW}  ├─────────────────────────────────────────────────────┤${NC}"
echo -e "${YELLOW}  │  Typ:   ${GREEN}A${YELLOW}                                           │${NC}"
echo -e "${YELLOW}  │  Host:  ${GREEN}${SLUG}${YELLOW}                                      │${NC}"
echo -e "${YELLOW}  │  Wert:  ${GREEN}${VPS_IP}${YELLOW}                                  │${NC}"
echo -e "${YELLOW}  │  TTL:   ${GREEN}3600${YELLOW}  (oder Standard)                       │${NC}"
echo -e "${YELLOW}  └─────────────────────────────────────────────────────┘${NC}"
echo ""
read -rp "  ENTER druecken, sobald der Eintrag gespeichert ist  [s = DNS ueberspringen]: " DNSANS

DNS_OK=0
if [[ "${DNSANS,,}" != "s" ]]; then
    echo -n "  Warte auf DNS-Verbreitung (max. 10 min) "
    for _ in $(seq 1 60); do
        RESOLVED="$(dig +short A "$FQDN" @1.1.1.1 2>/dev/null | grep -E '^[0-9]+\.[0-9]+' | tail -1)"
        if [[ "$RESOLVED" == "$VPS_IP" ]]; then
            DNS_OK=1; echo " ✔"; break
        fi
        echo -n "."; sleep 10
    done
    [[ "$DNS_OK" == "0" ]] && echo ""
fi

if [[ "$DNS_OK" == "0" ]]; then
    warn "DNS noch nicht aktiv. HTTPS wird uebersprungen."
    warn "Zertifikat spaeter nachholen:"
    info "certbot --nginx -d ${FQDN} --non-interactive --agree-tos -m ${LE_EMAIL} --redirect"
fi

# ── 9. HTTPS-Zertifikat ─────────────────────────────────────
HTTPS_OK=0
if [[ "$DNS_OK" == "1" ]]; then
    step "HTTPS-Zertifikat holen (Let's Encrypt)"
    if certbot --nginx -d "$FQDN" --non-interactive --agree-tos \
               -m "$LE_EMAIL" --redirect --keep-until-expiring; then
        systemctl reload nginx
        HTTPS_OK=1
        ok "HTTPS aktiv fuer $FQDN"
    else
        warn "Zertifikat fehlgeschlagen. Spaeter manuell nachholen:"
        info "certbot --nginx -d ${FQDN} --non-interactive --agree-tos -m ${LE_EMAIL} --redirect"
    fi
fi

# ── Fertig ──────────────────────────────────────────────────
SUCCESS=1
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Schule erfolgreich eingerichtet!        ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
if [[ "$HTTPS_OK" == "1" ]]; then
    echo -e "${GREEN}║${NC}  URL:   ${GREEN}https://${FQDN}${NC}"
else
    echo -e "${GREEN}║${NC}  URL:   ${YELLOW}http://${FQDN}${NC}  (HTTPS folgt)"
fi
echo -e "${GREEN}║${NC}  Port:  ${PORT}"
echo -e "${GREEN}║${NC}  DB:    ${DB_NAME}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  Beim ersten Aufruf startet der          "
echo -e "${GREEN}║${NC}  Einrichtungs-Assistent automatisch.     "
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  Verwaltung:"
echo "    Status:   systemctl status learngrid@${SLUG}"
echo "    Logs:     journalctl -u learngrid@${SLUG} -f"
echo "    Neustart: systemctl restart learngrid@${SLUG}"
echo ""
echo "  Alle Schulen anzeigen:"
echo "    bash $(realpath "$0") --list"
echo ""
