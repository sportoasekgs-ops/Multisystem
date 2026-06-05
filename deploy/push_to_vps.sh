#!/bin/bash
# ============================================================
#  LearnGrid – Code vom Entwicklungsrechner auf den VPS pushen
#  ----------------------------------------------------------
#  Aufruf (von deinem lokalen Rechner oder Replit Shell):
#
#    bash deploy/push_to_vps.sh                   # Code pushen + alle Schulen neu starten
#    bash deploy/push_to_vps.sh igs-badenstedt    # nur eine Schule aktualisieren
#    bash deploy/push_to_vps.sh --dry-run         # Vorschau ohne Aenderungen
#
#  Konfiguration (einmalig):
#    Erstelle die Datei deploy/.push_config mit:
#      VPS_HOST=root@87.106.155.5
#      VPS_SRC_DIR=/opt/learngrid
#
#    Oder setze Umgebungsvariablen:
#      export VPS_HOST=root@87.106.155.5
#      export VPS_SRC_DIR=/opt/learngrid
# ============================================================
set -euo pipefail

# ── Konfiguration laden ──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$SCRIPT_DIR/.push_config"

if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
fi

VPS_HOST="${VPS_HOST:-}"
VPS_SRC_DIR="${VPS_SRC_DIR:-/opt/learngrid}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()    { echo -e "${GREEN}✔ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $*${NC}"; }
err()   { echo -e "${RED}✘ $*${NC}"; exit 1; }
step()  { echo -e "\n${BLUE}▶ $*${NC}"; }
info()  { echo -e "${CYAN}  $*${NC}"; }

# ── VPS_HOST konfigurieren falls nicht gesetzt ───────────────
if [[ -z "$VPS_HOST" ]]; then
    echo ""
    warn "VPS_HOST ist nicht gesetzt."
    echo ""
    read -rp "  VPS SSH-Adresse (z.B. root@87.106.155.5): " VPS_HOST
    [[ -z "$VPS_HOST" ]] && err "VPS_HOST erforderlich"
    echo ""
    read -rp "  Konfiguration speichern in $CONFIG_FILE? [J/n]: " SAVE
    if [[ "${SAVE,,}" != "n" ]]; then
        cat > "$CONFIG_FILE" <<EOF
VPS_HOST="${VPS_HOST}"
VPS_SRC_DIR="${VPS_SRC_DIR}"
EOF
        ok "Gespeichert in $CONFIG_FILE"
        echo ""
        info "Hinweis: $CONFIG_FILE ist in .gitignore eingetragen (keine Zugangsdaten im Repo)."
    fi
fi

# ── Argumente parsen ─────────────────────────────────────────
DRY_RUN=0
ONLY_SLUG=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --*)       err "Unbekannte Option: $arg" ;;
        *)         ONLY_SLUG="$arg" ;;
    esac
done

# ── SSH-Verbindung testen ────────────────────────────────────
step "Verbindung zu $VPS_HOST pruefen"
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$VPS_HOST" "echo ok" >/dev/null 2>&1; then
    err "SSH-Verbindung zu $VPS_HOST fehlgeschlagen.\nHinweis: SSH-Key hinterlegt?  ssh-copy-id $VPS_HOST"
fi
ok "VPS erreichbar"

# ── Dry-run Hinweis ─────────────────────────────────────────
if [[ "$DRY_RUN" == "1" ]]; then
    warn "DRY-RUN Modus – keine Dateien werden veraendert"
fi

START_TIME="$(date +%s)"
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  LearnGrid – Push to VPS                 ║${NC}"
echo -e "${BLUE}╠══════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  Von:  $(hostname):${PROJECT_DIR}"
echo -e "${BLUE}║${NC}  Nach: ${VPS_HOST}:${VPS_SRC_DIR}"
[[ -n "$ONLY_SLUG" ]] && echo -e "${BLUE}║${NC}  Schule: ${ONLY_SLUG}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"

# ── Code per rsync auf den VPS uebertragen ───────────────────
step "Code uebertragen (rsync)"

RSYNC_OPTS=(-az --human-readable --progress)
[[ "$DRY_RUN" == "1" ]] && RSYNC_OPTS+=(--dry-run)

RSYNC_EXCLUDES=(
    --exclude='.git'
    --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo'
    --exclude='venv/' --exclude='.venv/'
    --exclude='node_modules/'
    --exclude='.env'
    --exclude='buchungssystem_local.json'
    --exclude='scratch/'
    --exclude='logs/'
    --exclude='static/uploads/'
    --exclude='deploy/.push_config'
    --exclude='*.log'
    --exclude='.replit' --exclude='.upm/' --exclude='.cache/'
    --exclude='.pythonlibs/' --exclude='.agents/'
)

rsync "${RSYNC_OPTS[@]}" "${RSYNC_EXCLUDES[@]}" \
    "$PROJECT_DIR"/ \
    "${VPS_HOST}:${VPS_SRC_DIR}/"

ok "Code uebertragen"

# ── Redeploy auf dem VPS ausfuehren ──────────────────────────
if [[ "$DRY_RUN" == "1" ]]; then
    warn "DRY-RUN: Redeploy wird nicht ausgefuehrt"
    echo ""
    ok "Dry-run abgeschlossen – keine Aenderungen vorgenommen"
    exit 0
fi

step "Redeploy auf VPS ausfuehren"
REDEPLOY_CMD="bash ${VPS_SRC_DIR}/deploy/redeploy.sh --no-pull"
[[ -n "$ONLY_SLUG" ]] && REDEPLOY_CMD="$REDEPLOY_CMD $ONLY_SLUG"

# SSH mit Pseudo-TTY fuer farbige Ausgabe
ssh -t "$VPS_HOST" "$REDEPLOY_CMD"

ELAPSED=$(( $(date +%s) - START_TIME ))
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Push + Redeploy abgeschlossen!          ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  ⏱  ${ELAPSED}s gesamt"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
