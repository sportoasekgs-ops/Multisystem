#!/bin/bash
# ============================================================
#  LearnGrid – Redeploy / Update auf dem VPS
#  ----------------------------------------------------------
#  Aufruf (als root):
#      bash redeploy.sh              # Code holen + alle Instanzen aktualisieren
#      bash redeploy.sh --no-pull    # ohne git pull (Code bereits aktuell)
#      bash redeploy.sh igs-badenstedt   # nur eine bestimmte Schule
#
#  Aktualisiert:
#    1. Quellcode in /opt/buchungssystem (git pull, falls Repo)
#    2. Gemeinsame Python-Umgebung (/srv/learngrid/venv)
#    3. Jede Schul-Instanz unter /srv/learngrid/<slug>
#       (Code neu synchronisiert, Service neu gestartet)
#    4. Den alten Einzel-Service "buchungssystem" (falls vorhanden)
#
#  Pro Schule bleiben .env, buchungssystem_local.json und
#  static/uploads (Logos) unberuehrt.
# ============================================================
set -euo pipefail

SRC_DIR="${SRC_DIR:-/opt/buchungssystem}"
BASE_ROOT="/srv/learngrid"
SHARED_VENV="$BASE_ROOT/venv"
LEGACY_SERVICE="buchungssystem"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}\xe2\x9c\x94 $1${NC}"; }
warn() { echo -e "${YELLOW}\xe2\x9a\xa0 $1${NC}"; }
err()  { echo -e "${RED}\xe2\x9c\x98 $1${NC}"; exit 1; }
step() { echo -e "\n${BLUE}\xe2\x96\xb6 $1${NC}"; }

[[ $EUID -ne 0 ]] && err "Bitte als root ausfuehren:  sudo bash redeploy.sh"
[[ -d "$SRC_DIR" ]] || err "Quellcode nicht gefunden in $SRC_DIR (SRC_DIR anpassen)"

# ── Argumente ───────────────────────────────────────────────
DO_PULL=1
ONLY_SLUG=""
for arg in "$@"; do
    case "$arg" in
        --no-pull) DO_PULL=0 ;;
        -*) err "Unbekannte Option: $arg" ;;
        *)  ONLY_SLUG="$arg" ;;
    esac
done

# Gemeinsame Ausschluss-Liste: pro Instanz eigene Daten NICHT ueberschreiben
RSYNC_EXCLUDES=(
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc'
    --exclude='venv' --exclude='.venv' --exclude='node_modules'
    --exclude='.env' --exclude='buchungssystem_local.json'
    --exclude='scratch' --exclude='logs'
    --exclude='static/uploads'
)

# ── 1. Quellcode aktualisieren ──────────────────────────────
step "Quellcode aktualisieren"
cd "$SRC_DIR"
if [[ "$DO_PULL" == "1" && -d "$SRC_DIR/.git" ]]; then
    git pull
    ok "Code aktualisiert (git pull)"
elif [[ "$DO_PULL" == "1" ]]; then
    warn "Kein git-Repo in $SRC_DIR – ueberspringe pull (Code muss bereits aktuell sein)"
else
    warn "git pull uebersprungen (--no-pull)"
fi

# ── 2. Gemeinsame Python-Umgebung aktualisieren ─────────────
step "Abhaengigkeiten aktualisieren"
if [[ -x "$SHARED_VENV/bin/pip" ]]; then
    "$SHARED_VENV/bin/pip" install --quiet --upgrade -r "$SRC_DIR/requirements.txt"
    ok "Gemeinsame Umgebung aktuell"
else
    warn "Keine gemeinsame Umgebung in $SHARED_VENV (noch keine Schule per provision_school.sh angelegt?)"
fi
# Legacy-venv des alten Einzel-Service (falls vorhanden)
if [[ -x "$SRC_DIR/venv/bin/pip" ]]; then
    "$SRC_DIR/venv/bin/pip" install --quiet --upgrade -r "$SRC_DIR/requirements.txt"
    ok "Legacy-Umgebung aktuell"
fi

# ── 3. Schul-Instanzen aktualisieren ────────────────────────
step "Schul-Instanzen aktualisieren"
UPDATED=0
FAILED=0
FOUND=0
if [[ -d "$BASE_ROOT" ]]; then
    shopt -s nullglob
    for d in "$BASE_ROOT"/*/; do
        slug="$(basename "$d")"
        [[ "$slug" == "venv" ]] && continue
        [[ -f "$d/.env" ]] || continue
        [[ -n "$ONLY_SLUG" && "$slug" != "$ONLY_SLUG" ]] && continue
        FOUND=$((FOUND + 1))

        echo -e "  ${BLUE}\xe2\x80\xa2 $slug${NC}"
        # --delete haelt die Instanz exakt zum Quellcode; ausgeschlossene
        # Dateien (.env, uploads, ...) werden NICHT geloescht.
        rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$SRC_DIR"/ "$d"
        mkdir -p "$d/static/uploads" "$d/logs"
        chown -R www-data:www-data "$d"

        # Existiert die Service-Unit ueberhaupt? (Template oder Instanz)
        if ! systemctl cat "learngrid@${slug}" >/dev/null 2>&1; then
            warn "  Service learngrid@${slug} nicht installiert – uebersprungen (provision_school.sh erneut ausfuehren?)"
            FAILED=$((FAILED + 1))
            continue
        fi

        if systemctl restart "learngrid@${slug}" && { sleep 2; systemctl is-active --quiet "learngrid@${slug}"; }; then
            ok "  $slug neu gestartet"
            UPDATED=$((UPDATED + 1))
        else
            warn "  $slug startet nicht – pruefe: journalctl -u learngrid@${slug} -n 40"
            FAILED=$((FAILED + 1))
        fi
    done
fi

if [[ -n "$ONLY_SLUG" && "$FOUND" == "0" ]]; then
    err "Schule '$ONLY_SLUG' nicht gefunden unter $BASE_ROOT (kein Verzeichnis mit .env)."
fi
if [[ "$FOUND" == "0" && -z "$ONLY_SLUG" ]]; then
    warn "Keine Schul-Instanzen unter $BASE_ROOT gefunden"
fi

# ── 4. Alten Einzel-Service aktualisieren (falls vorhanden) ──
if [[ -z "$ONLY_SLUG" ]] && systemctl list-unit-files 2>/dev/null | grep -q "^${LEGACY_SERVICE}\.service"; then
    step "Alten Einzel-Service neu starten"
    if systemctl restart "$LEGACY_SERVICE"; then
        sleep 2
        if systemctl is-active --quiet "$LEGACY_SERVICE"; then
            ok "$LEGACY_SERVICE neu gestartet"
        else
            warn "$LEGACY_SERVICE startet nicht – pruefe: journalctl -u $LEGACY_SERVICE -n 40"
            FAILED=$((FAILED + 1))
        fi
    fi
fi

# ── Fertig ──────────────────────────────────────────────────
echo ""
if [[ "$FAILED" == "0" ]]; then
    ok "Redeploy abgeschlossen ($UPDATED Instanz(en) aktualisiert)"
else
    warn "Redeploy abgeschlossen – $FAILED Instanz(en) mit Problemen. Bitte Logs pruefen."
    exit 1
fi
