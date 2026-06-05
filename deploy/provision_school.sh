#!/bin/bash
# ============================================================
#  LearnGrid – Neue Schule automatisch anlegen
#  ----------------------------------------------------------
#  Aufruf (als root):
#      bash provision_school.sh "IGS Badenstedt"
#
#  Legt fuer die Schule vollautomatisch an:
#    1. Eigene PostgreSQL-Datenbank (lokal auf dem VPS)
#    2. Eigene, isolierte App-Instanz (eigenes Verzeichnis + Port)
#    3. systemd-Service (startet automatisch, Auto-Restart)
#    4. nginx-vhost fuer die Subdomain
#    5. HTTPS-Zertifikat (Let's Encrypt)
#
#  EINZIGER manueller Schritt: den A-Record der Subdomain bei
#  IONOS anlegen. Das Skript sagt dir exakt was einzutragen ist
#  und wartet automatisch, bis er aktiv ist.
# ============================================================
set -euo pipefail

# ── Grundkonfiguration (einmalig anpassbar) ─────────────────
SRC_DIR="${SRC_DIR:-/opt/buchungssystem}"      # Wo der LearnGrid-Code liegt
BASE_ROOT="/srv/learngrid"                      # Wurzel fuer alle Instanzen
SHARED_VENV="$BASE_ROOT/venv"                   # gemeinsame Python-Umgebung
CONF_FILE="/etc/learngrid/provision.conf"       # gespeicherte Einstellungen
PORT_START=8001                                 # erster Instanz-Port

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}\xe2\x9c\x94 $1${NC}"; }
warn() { echo -e "${YELLOW}\xe2\x9a\xa0 $1${NC}"; }
err()  { echo -e "${RED}\xe2\x9c\x98 $1${NC}"; exit 1; }
step() { echo -e "\n${BLUE}\xe2\x96\xb6 $1${NC}"; }

[[ $EUID -ne 0 ]] && err "Bitte als root ausfuehren:  sudo bash provision_school.sh \"Schulname\""

SCHOOL_NAME="${1:-}"
[[ -z "$SCHOOL_NAME" ]] && err "Bitte den Schulnamen angeben:  bash provision_school.sh \"IGS Badenstedt\""

# ── Lock: verhindert parallele Provisionierungslaeufe ───────
LOCK_FILE="/var/lock/learngrid-provision.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    err "Eine andere Provisionierung laeuft gerade. Bitte warten und erneut versuchen."
fi

# ── Rollback bei Fehler (nur in diesem Lauf erstellte Dinge) ─
SUCCESS=0
CREATED_DB=0; CREATED_DIR=0; CREATED_UNIT=0; CREATED_NGINX=0
cleanup() {
    [[ "$SUCCESS" == "1" ]] && return
    echo ""
    warn "Fehler erkannt – mache angelegte Ressourcen rueckgaengig ..."
    if [[ "$CREATED_NGINX" == "1" ]]; then
        rm -f "/etc/nginx/sites-enabled/learngrid-${SLUG}" "/etc/nginx/sites-available/learngrid-${SLUG}"
        nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
    fi
    if [[ "$CREATED_UNIT" == "1" ]]; then
        systemctl disable --now "learngrid@${SLUG}" >/dev/null 2>&1 || true
    fi
    [[ "$CREATED_DIR" == "1" ]] && rm -rf "$INSTANCE_DIR"
    if [[ "$CREATED_DB" == "1" ]]; then
        sudo -u postgres psql -v ON_ERROR_STOP=1 >/dev/null 2>&1 <<SQL || true
DROP DATABASE IF EXISTS "$DB_NAME";
DROP USER IF EXISTS "$DB_USER";
SQL
    fi
    warn "Rueckgaengig gemacht. Du kannst das Skript erneut ausfuehren."
}
trap cleanup EXIT

# ── Gespeicherte Einstellungen laden / erfragen ─────────────
mkdir -p "$(dirname "$CONF_FILE")"
# shellcheck disable=SC1090
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
    read -rp "  E-Mail fuer Let's Encrypt (Zertifikats-Hinweise): " LE_EMAIL
    [[ -z "$LE_EMAIL" ]] && err "E-Mail fuer Let's Encrypt erforderlich"
fi

cat > "$CONF_FILE" <<EOF
BASE_DOMAIN="$BASE_DOMAIN"
VPS_IP="$VPS_IP"
LE_EMAIL="$LE_EMAIL"
EOF
chmod 600 "$CONF_FILE"

# ── Slug / Subdomain aus dem Schulnamen ableiten ────────────
SLUG="$(printf '%s' "$SCHOOL_NAME" \
    | sed -e 's/\xc3\x84/Ae/g; s/\xc3\x96/Oe/g; s/\xc3\x9c/Ue/g; s/\xc3\xa4/ae/g; s/\xc3\xb6/oe/g; s/\xc3\xbc/ue/g; s/\xc3\x9f/ss/g' \
    | tr '[:upper:]' '[:lower:]' \
    | sed -e 's/[^a-z0-9]\+/-/g; s/^-\+//; s/-\+$//')"
# Optionaler 2. Parameter ueberschreibt den automatischen Slug
[[ -n "${2:-}" ]] && SLUG="$2"
[[ -z "$SLUG" ]] && err "Konnte aus dem Schulnamen keinen gueltigen Subdomain-Namen ableiten"

# Strenge Validierung (DNS-Label-Regeln) – verhindert ungueltige FQDN/DB-Namen
# sowie Injektion ueber den optionalen Slug-Parameter
if ! [[ "$SLUG" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
    err "Ungueltiger Subdomain-Name '$SLUG' (erlaubt: a-z, 0-9, Bindestrich; nicht am Anfang/Ende)."
fi

FQDN="${SLUG}.${BASE_DOMAIN}"
INSTANCE_DIR="$BASE_ROOT/$SLUG"
DB_NAME="learngrid_$(echo "$SLUG" | tr '-' '_')"
DB_USER="$DB_NAME"

echo ""
echo -e "${BLUE}\xe2\x95\x94\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x97${NC}"
echo -e "${BLUE}  Neue Schule:${NC} $SCHOOL_NAME"
echo -e "${BLUE}  Adresse:    ${NC} https://$FQDN"
echo -e "${BLUE}  Datenbank:  ${NC} $DB_NAME"
echo -e "${BLUE}\xe2\x95\x9a\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x9d${NC}"

if [[ -d "$INSTANCE_DIR" ]]; then
    err "Instanz '$SLUG' existiert bereits ($INSTANCE_DIR). Bitte anderen Namen/Slug waehlen."
fi

# ── 0. Systempakete sicherstellen ───────────────────────────
step "Systempakete pruefen"
NEED_PKGS=()
command -v nginx     >/dev/null || NEED_PKGS+=(nginx)
command -v psql      >/dev/null || NEED_PKGS+=(postgresql)
command -v certbot   >/dev/null || NEED_PKGS+=(certbot python3-certbot-nginx)
command -v rsync     >/dev/null || NEED_PKGS+=(rsync)
command -v dig       >/dev/null || NEED_PKGS+=(dnsutils)
python3 -m venv --help >/dev/null 2>&1 || NEED_PKGS+=(python3-venv)
if [[ ${#NEED_PKGS[@]} -gt 0 ]]; then
    warn "Installiere: ${NEED_PKGS[*]}"
    apt-get update -qq
    apt-get install -y -qq "${NEED_PKGS[@]}"
fi
systemctl enable --now postgresql >/dev/null 2>&1 || true
ok "Pakete bereit"

[[ -d "$SRC_DIR" ]] || err "Quellcode nicht gefunden in $SRC_DIR (SRC_DIR anpassen)"

# ── 1. PostgreSQL-Datenbank anlegen ─────────────────────────
step "Datenbank anlegen"
DB_PASS="$(openssl rand -hex 24)"
DB_EXISTS="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")"
if [[ "$DB_EXISTS" == "1" ]]; then
    err "Datenbank $DB_NAME existiert bereits. Bitte zuerst aufraeumen."
fi
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE USER "$DB_USER" WITH PASSWORD '$DB_PASS';
CREATE DATABASE "$DB_NAME" OWNER "$DB_USER";
GRANT ALL PRIVILEGES ON DATABASE "$DB_NAME" TO "$DB_USER";
SQL
CREATED_DB=1
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
ok "Datenbank $DB_NAME + Benutzer angelegt"

# ── 2. Instanz-Verzeichnis (isolierte Kopie des Codes) ──────
step "App-Instanz vorbereiten"
mkdir -p "$INSTANCE_DIR"
CREATED_DIR=1
rsync -a \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='venv' --exclude='.venv' --exclude='node_modules' \
    --exclude='.env' --exclude='buchungssystem_local.json' \
    --exclude='scratch' --exclude='logs' \
    "$SRC_DIR"/ "$INSTANCE_DIR"/
mkdir -p "$INSTANCE_DIR/static/uploads" "$INSTANCE_DIR/logs"
ok "Code nach $INSTANCE_DIR kopiert"

# ── 3. Gemeinsame Python-Umgebung (einmalig) ────────────────
step "Python-Umgebung pruefen"
if [[ ! -x "$SHARED_VENV/bin/gunicorn" ]]; then
    warn "Erstelle gemeinsame Umgebung in $SHARED_VENV (einmalig, kann dauern)"
    python3 -m venv "$SHARED_VENV"
    "$SHARED_VENV/bin/pip" install --quiet --upgrade pip
    "$SHARED_VENV/bin/pip" install --quiet -r "$INSTANCE_DIR/requirements.txt"
fi
ok "Python-Umgebung bereit"

# ── 4. Freien Port waehlen ──────────────────────────────────
step "Port zuweisen"
USED_PORTS="$(grep -rhoE '^PORT=[0-9]+' "$BASE_ROOT"/*/.env 2>/dev/null | cut -d= -f2 || true)"
PORT=$PORT_START
while echo "$USED_PORTS" | grep -qx "$PORT" || ss -tlnH "sport = :$PORT" 2>/dev/null | grep -q .; do
    PORT=$((PORT + 1))
done
ok "Port $PORT"

# ── 5. Umgebungsdatei der Instanz ───────────────────────────
SESSION_SECRET="$(openssl rand -hex 32)"
cat > "$INSTANCE_DIR/.env" <<EOF
DATABASE_URL=${DATABASE_URL}
SESSION_SECRET=${SESSION_SECRET}
PORT=${PORT}
FLASK_ENV=production
EOF
chmod 600 "$INSTANCE_DIR/.env"
chown -R www-data:www-data "$INSTANCE_DIR"
ok "Konfiguration geschrieben"

# ── 6. systemd-Service ──────────────────────────────────────
step "systemd-Service einrichten"
TEMPLATE_UNIT="/etc/systemd/system/learngrid@.service"
if [[ ! -f "$TEMPLATE_UNIT" ]]; then
    cat > "$TEMPLATE_UNIT" <<EOF
[Unit]
Description=LearnGrid Instanz %i
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$BASE_ROOT/%i
EnvironmentFile=$BASE_ROOT/%i/.env
ExecStart=$SHARED_VENV/bin/gunicorn --chdir $BASE_ROOT/%i --bind 127.0.0.1:\${PORT} --workers 3 --timeout 120 main:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
fi
systemctl enable --now "learngrid@${SLUG}" >/dev/null 2>&1
CREATED_UNIT=1
sleep 3
if systemctl is-active --quiet "learngrid@${SLUG}"; then
    ok "Service learngrid@${SLUG} laeuft (Port $PORT)"
else
    err "Service startet nicht. Pruefe:  journalctl -u learngrid@${SLUG} -n 40"
fi

# ── 7. nginx-vhost (zunaechst HTTP, fuer Zertifikatsausstellung) ─
step "nginx konfigurieren"
NGINX_SITE="/etc/nginx/sites-available/learngrid-${SLUG}"
cat > "$NGINX_SITE" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${FQDN};

    client_max_body_size 16M;

    location /.well-known/acme-challenge/ { root /var/www/html; }

    location /static/ {
        alias ${INSTANCE_DIR}/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass         http://127.0.0.1:${PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }
}
EOF
mkdir -p /var/www/html
ln -sf "$NGINX_SITE" "/etc/nginx/sites-enabled/learngrid-${SLUG}"
CREATED_NGINX=1
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "nginx-vhost fuer $FQDN aktiv"

# ── 8. Subdomain bei IONOS (manuell) + warten ───────────────
step "DNS-Eintrag (einziger manueller Schritt)"
echo ""
echo -e "${YELLOW}  Lege bei IONOS in der Domain '${BASE_DOMAIN}' diesen Eintrag an:${NC}"
echo -e "      Typ:    ${GREEN}A${NC}"
echo -e "      Host:   ${GREEN}${SLUG}${NC}   (ergibt ${SLUG}.${BASE_DOMAIN})"
echo -e "      Wert:   ${GREEN}${VPS_IP}${NC}"
echo -e "      TTL:    3600 (oder Standard)"
echo ""
read -rp "  ENTER druecken, sobald der Eintrag gespeichert ist (oder 's' = ueberspringen): " DNSANS

DNS_OK=0
if [[ "$DNSANS" != "s" && "$DNSANS" != "S" ]]; then
    echo -n "  Warte auf DNS-Verbreitung "
    for _ in $(seq 1 60); do
        RESOLVED="$(dig +short A "$FQDN" @1.1.1.1 2>/dev/null | tail -n1)"
        if [[ "$RESOLVED" == "$VPS_IP" ]]; then DNS_OK=1; break; fi
        echo -n "."
        sleep 10
    done
    echo ""
fi

if [[ "$DNS_OK" == "1" ]]; then
    ok "DNS zeigt auf $VPS_IP"
else
    warn "DNS noch nicht aktiv. HTTPS wird uebersprungen."
    warn "Sobald der A-Record greift, manuell holen:"
    echo  "    certbot --nginx -d ${FQDN} --non-interactive --agree-tos -m ${LE_EMAIL} --redirect"
fi

# ── 9. HTTPS-Zertifikat ─────────────────────────────────────
HTTPS_OK=0
if [[ "$DNS_OK" == "1" ]]; then
    step "HTTPS-Zertifikat holen"
    if certbot --nginx -d "$FQDN" --non-interactive --agree-tos -m "$LE_EMAIL" --redirect; then
        systemctl reload nginx
        HTTPS_OK=1
        ok "HTTPS aktiv fuer $FQDN"
    else
        warn "Zertifikat fehlgeschlagen. Spaeter erneut versuchen:"
        echo "    certbot --nginx -d ${FQDN} --non-interactive --agree-tos -m ${LE_EMAIL} --redirect"
    fi
fi

# ── Fertig ──────────────────────────────────────────────────
SUCCESS=1
echo ""
echo -e "${GREEN}\xe2\x95\x94\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x97${NC}"
echo -e "${GREEN}  Schule eingerichtet!${NC}"
if [[ "$HTTPS_OK" == "1" ]]; then
    echo -e "  Adresse:  ${GREEN}https://${FQDN}${NC}"
else
    echo -e "  Adresse:  ${YELLOW}http://${FQDN}${NC}  (HTTPS sobald DNS/Zertifikat steht)"
fi
echo -e "  Beim ersten Aufruf fuehrt der Einrichtungs-Assistent durch den Rest."
echo -e "${GREEN}\xe2\x95\x9a\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x9d${NC}"
echo ""
echo "  Verwaltung dieser Instanz:"
echo "    Status:    systemctl status learngrid@${SLUG}"
echo "    Logs:      journalctl -u learngrid@${SLUG} -f"
echo "    Neustart:  systemctl restart learngrid@${SLUG}"
echo ""
