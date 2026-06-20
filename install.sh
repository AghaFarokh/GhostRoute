#!/usr/bin/env bash
# USDT GhostRoute — Auto Installer for Ubuntu/Debian
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run this script as root: sudo bash install.sh"

INSTALL_DIR="/root/iraniexchange"
SERVICE_NAME="iraniexchange"
PYTHON_MIN="3.10"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      USDT GhostRoute — Installer         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
info "Updating package lists..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    curl gnupg build-essential libssl-dev > /dev/null

# ── 2. MongoDB ────────────────────────────────────────────────────────────────
if ! command -v mongod &>/dev/null; then
    info "Installing MongoDB 7.0..."
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc \
        | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg

    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/7.0 multiverse" \
        > /etc/apt/sources.list.d/mongodb-org-7.0.list

    apt-get update -qq
    apt-get install -y -qq mongodb-org > /dev/null
    systemctl enable mongod --now
    success "MongoDB installed and started."
else
    systemctl enable mongod --now 2>/dev/null || true
    success "MongoDB already installed."
fi

# ── 3. Project directory ──────────────────────────────────────────────────────
info "Setting up project directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy files from current directory if running from source
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in main.py lang.py requirements.txt; do
    if [[ -f "$SCRIPT_DIR/$f" ]]; then
        cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
    fi
done

# ── 4. Python virtual environment ─────────────────────────────────────────────
info "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

info "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q
success "Python dependencies installed."

# ── 5. Generate encryption key ────────────────────────────────────────────────
info "Generating Fernet encryption key..."
ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
success "Encryption key generated."

# ── 6. .env configuration ─────────────────────────────────────────────────────
ENV_FILE="$INSTALL_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists — skipping prompt. Edit $ENV_FILE manually if needed."
else
    echo ""
    echo "──────────────────────────────────────────"
    echo "  Bot Configuration"
    echo "──────────────────────────────────────────"
    read -rp "  Telegram Bot Token  : " BOT_TOKEN
    read -rp "  Admin Telegram ID(s) (comma-separated): " ADMIN_IDS

    cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
MONGO_URI=mongodb://localhost:27017
ENCRYPTION_KEY=${ENC_KEY}
ADMIN_IDS=${ADMIN_IDS}
EOF
    chmod 600 "$ENV_FILE"
    success ".env created at $ENV_FILE"
fi

# ── 7. Systemd service ────────────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=USDT GhostRoute
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

success "Systemd service '${SERVICE_NAME}' enabled and started."

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        Installation Complete!            ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Config : $ENV_FILE"
echo "  Logs   : journalctl -u ${SERVICE_NAME} -f"
echo "  Status : systemctl status ${SERVICE_NAME}"
echo "  Stop   : systemctl stop ${SERVICE_NAME}"
echo "  Start  : systemctl start ${SERVICE_NAME}"
echo ""
