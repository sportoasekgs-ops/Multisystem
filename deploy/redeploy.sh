#!/bin/bash
# ============================================================
#  LearnGrid – Patch / Update auf dem VPS
#  ----------------------------------------------------------
#  Aufruf (als root auf dem VPS):
#
#    bash redeploy.sh                  # alle Schulen aktualisieren
#    bash redeploy.sh igs-badenstedt   # nur eine bestimmte Schule
#    bash redeploy.sh --no-pull        # kein git pull (Code bereits aktuell)
#    bash redeploy.sh --status         # Uebersicht ohne Update
#
#  Was passiert:
#    1. Quellcode in /opt/learngrid aktualisieren (git pull)
#    2. Python-Pakete in der gemeinsamen Umgebung updaten
#    3. Code in jede Schul-Instanz rsync-en
#    4. Jeden Service neu starten, Gesundheitscheck
#
#  Pro Schule bleiben unveraendert:
#    .env, buchungssystem_local.json, static/uploads (Logos)
# ============================================================
set -euo pipefail

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

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
err()  { echo -e "${RED}✘ $*${NC}"; exit 1; }
step() { echo -e "\n${BLUE}▶ $*${NC}"; }
info() { echo -e "${CYAN}  $*${NC}"; }

[[ $EUID -ne 0 ]] && err "Bitte als root ausfuehren:  sudo bash redeploy.sh"

# ── Argumente parsen ────────────────────────────────────────
DO_PULL=1
ONLY_SLUG=""
STATUS_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --no-pull)  DO_PULL=0 ;;
        --status)   STATUS_ONLY=1 ;;
        --*)        err "Unbekannte Option: $arg" ;;
        *)          ONLY_SLUG="$arg" ;;
    esac
done

# ── --status: Uebersicht anzeigen ───────────────────────────
if [[ "$STATUS_ONLY" == "1" ]]; then
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  LearnGrid – Status aller Instanzen                  ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    FOUND=0
    if [[ -d "$BASE_ROOT" ]]; then
        for d in "$BASE_ROOT"/*/; do
            slug="$(basename "$d")"
            [[ "$slug" == "venv" ]] && continue
            [[ -f "$d/.env" ]] || continue
            FOUND=$((FOUND+1))
            PORT="$(grep '^PORT=' "$d/.env" 2>/dev/null | cut -d= -f2 || echo '?')"
            STATUS="$(systemctl is-active "learngrid@${slug}" 2>/dev/null || echo 'inaktiv')"
            UPTIME="$(systemctl show "learngrid@${slug}" -p ActiveEnterTimestamp 2>/dev/null \
                      | sed 's/ActiveEnterTimestamp=//' | xargs || echo '')"
            [[ "$STATUS" == "active" ]] && COL="$GREEN" || COL="$RED"
            printf "  %-30s  Port: %-6s  %b%s%b\n" "$slug" "$PORT" "$COL" "$STATUS" "$NC"
            [[ -n "$UPTIME" ]] && echo -e "    ${CYAN}seit: ${UPTIME}${NC}"
        done
    fi
    [[ "$FOUND" == "0" ]] && warn "Keine Instanzen unter $BASE_ROOT"
    echo ""
    exit 0
fi

# ── Quellcode-Verzeichnis pruefen ───────────────────────────
[[ -d "$SRC_DIR" ]] || err "Quellcode nicht gefunden in $SRC_DIR (SRC_DIR= anpassen)"

RSYNC_EXCLUDES=(
    --exclude='.git'
    --exclude='__pycache__' --exclude='*.pyc'
    --exclude='venv' --exclude='.venv'
    --exclude='node_modules'
    --exclude='.env'
    --exclude='buchungssystem_local.json'
    --exclude='scratch'
    --exclude='logs'
    --exclude='static/uploads'
    --exclude='deploy'
)

START_TIME="$(date +%s)"
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  LearnGrid – Patch / Redeploy            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"

# ── 1. Quellcode aktualisieren ──────────────────────────────
step "Quellcode aktualisieren"
cd "$SRC_DIR"
if [[ "$DO_PULL" == "1" && -d "$SRC_DIR/.git" ]]; then
    git fetch --quiet
    LOCAL="$(git rev-parse HEAD)"
    REMOTE="$(git rev-parse @{u} 2>/dev/null || echo '')"
    if [[ -n "$REMOTE" && "$LOCAL" != "$REMOTE" ]]; then
        git pull
        NEW_HASH="$(git rev-parse --short HEAD)"
        ok "Code aktualisiert → $NEW_HASH"
    else
        ok "Code bereits aktuell ($(git rev-parse --short HEAD))"
    fi
elif [[ "$DO_PULL" == "1" ]]; then
    warn "Kein git-Repo in $SRC_DIR – ueberspringe pull"
else
    ok "git pull uebersprungen (--no-pull)"
fi

# ── 2. Python-Pakete aktualisieren ──────────────────────────
step "Python-Pakete aktualisieren"
if [[ -x "$SHARED_VENV/bin/pip" ]]; then
    "$SHARED_VENV/bin/pip" install --quiet --upgrade -r "$SRC_DIR/requirements.txt"
    ok "Gemeinsame Python-Umgebung aktuell"
else
    warn "Keine gemeinsame Umgebung in $SHARED_VENV gefunden"
    warn "Wurde schon mindestens eine Schule per provision_school.sh angelegt?"
fi

# ── 3. Schul-Instanzen aktualisieren ────────────────────────
step "Schul-Instanzen aktualisieren"
UPDATED=0; FAILED=0; FOUND=0
if [[ -d "$BASE_ROOT" ]]; then
    shopt -s nullglob
    for d in "$BASE_ROOT"/*/; do
        slug="$(basename "$d")"
        [[ "$slug" == "venv" ]] && continue
        [[ -f "$d/.env" ]] || continue
        [[ -n "$ONLY_SLUG" && "$slug" != "$ONLY_SLUG" ]] && continue
        FOUND=$((FOUND+1))

        echo -e "\n  ${BLUE}• $slug${NC}"

        # Code synchronisieren (schont .env, uploads, logs)
        rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$SRC_DIR"/ "$d"
        mkdir -p "$d/static/uploads" "$d/logs"
        chown -R www-data:www-data "$d"

        # Service neu starten
        if ! systemctl cat "learngrid@${slug}" >/dev/null 2>&1; then
            warn "  Service learngrid@${slug} nicht gefunden – uebersprungen"
            warn "  (provision_school.sh erneut ausfuehren?)"
            FAILED=$((FAILED+1))
            continue
        fi

        systemctl restart "learngrid@${slug}"
        sleep 2

        if systemctl is-active --quiet "learngrid@${slug}"; then
            PORT="$(grep '^PORT=' "$d/.env" 2>/dev/null | cut -d= -f2 || echo '?')"
            ok "  $slug laeuft  (Port $PORT)"
            UPDATED=$((UPDATED+1))
        else
            warn "  $slug startet nicht"
            info "  Log: journalctl -u learngrid@${slug} -n 30 --no-pager"
            FAILED=$((FAILED+1))
        fi
    done
fi

if [[ -n "$ONLY_SLUG" && "$FOUND" == "0" ]]; then
    err "Schule '$ONLY_SLUG' nicht gefunden unter $BASE_ROOT"
fi
if [[ "$FOUND" == "0" && -z "$ONLY_SLUG" ]]; then
    warn "Keine Schul-Instanzen unter $BASE_ROOT gefunden"
    info "Erste Schule anlegen: bash deploy/provision_school.sh \"Schulname\""
fi

# ── Zusammenfassung ─────────────────────────────────────────
ELAPSED=$(( $(date +%s) - START_TIME ))
echo ""
if [[ "$FAILED" == "0" && "$FOUND" -gt 0 ]]; then
    echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  Patch abgeschlossen!                    ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  ✔  $UPDATED Instanz(en) aktualisiert"
    echo -e "${GREEN}║${NC}  ⏱  ${ELAPSED}s"
    echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
else
    [[ "$FAILED" -gt 0 ]] && warn "$FAILED Instanz(en) mit Problemen – Logs pruefen"
    [[ "$UPDATED" -gt 0 ]] && ok "$UPDATED Instanz(en) erfolgreich aktualisiert"
    [[ "$FAILED" -gt 0 ]] && exit 1
fi
echo ""
