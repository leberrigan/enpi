#!/usr/bin/env bash
set -e

HOME_DIR="/home/gnome"
LOG_DIR="/var/log/enpi"
DATA_DIR="/data/enpi"
ENPI_DIR="/opt/sensorgnome/enpi"
CTRL_DIR="/opt/sensorgnome/control"

ENPI_REPO="enpi"
ENPI_BRANCH="sensorgnome"
CTRL_REPO="sensorgnome-control"
CTRL_BRANCH=${1:-"enpi"}

SERVICE_USER="gnome"


echo "=== enpi Installer ==="

# 1. Ensure required packages
echo "[1/8] Installing system dependencies..."
sudo rm -f /etc/apt/sources.list.d/*bullseye-backports*.list
sudo apt update || true
sudo apt install -y python3-full python3-venv git i2c-tools pigpio

# 2. Add service user to required groups
sudo usermod -aG gpio,i2c,dialout "$SERVICE_USER"

# 3. Install code into /opt/enpi
echo "[3/8] Installing code into $ENPI_DIR..."

cd "$HOME_DIR"
git clone https://github.com/sensorgnome-org/"$ENPI_REPO".git
cd "$ENPI_REPO"
git checkout "$ENPI_BRANCH"

sudo touch /etc/sensorgnome/secrets.env

sudo mkdir -p "$ENPI_DIR"
sudo rsync -av --delete ./ "$ENPI_DIR"/
sudo chown -R "$SERVICE_USER":"$SERVICE_USER" "$ENPI_DIR"


# 4. Create data + log directories
echo "[4/8] Creating data and log directories..."
sudo mkdir -p "$DATA_DIR"
sudo mkdir -p "$LOG_DIR"
sudo chown -R "$SERVICE_USER":"$SERVICE_USER" "$LOG_DIR"


# 5. Python virtual environment
echo "[5/8] Setting up Python virtual environment..."
sudo -u "$SERVICE_USER" bash <<EOF
cd "$ENPI_DIR"
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi
EOF

# 6. Pigpio service
echo "[6/8] Setting up services..."

sudo tee /etc/systemd/system/pigpiod.service > /dev/null <<EOF
[Unit]
Description=Pigpio Daemon
After=network.target

[Service]
Type=forking
ExecStart=/usr/bin/pigpiod
ExecStop=/bin/systemctl kill pigpiod

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

#6. udev rules
echo "[7/8] Installing udev rules..."
# Copy rules from repo to system directory
sudo cp "$ENPI_DIR/udev/10-enpi.rules" /etc/udev/rules.d/
# Ensure correct permissions
sudo chmod 644 /etc/udev/rules.d/10-enpi.rules
# Disable conflicting rules
sudo sed -i \
  's|^SUBSYSTEM=="tty",ATTRS{idVendor}=="0403",ATTRS{idProduct}=="6001"|# &|' \
  /etc/udev/rules.d/20-usb-hub-devices.rules

# Reload and trigger
sudo udevadm control --reload-rules
sudo udevadm trigger


#7. Clone and install sg-control repo
echo "[8/8] Installing custom sg-control software"
cd "$HOME_DIR"
git clone "https://github.com/leberrigan/$CTRL_REPO.git"
cd "$CTRL_REPO"
git switch "$CTRL_BRANCH"

sudo mv "acquisition.json" /etc/sensorgnome/
sudo mv "src/dashboard.js" "$CTRL_DIR"
sudo mv "src/enpi.js" "$CTRL_DIR"
sudo mv "src/fd-config.json" "$CTRL_DIR"
sudo mv "src/main.js" "$CTRL_DIR"
sudo mv "src/motus_up.js" "$CTRL_DIR"

sudo systemctl restart sg-control

echo "=== Installation complete ==="
echo "Logs: $LOG_DIR"
echo "Data: $DATA_DIR"
echo "Services: pigpio"

read -t 10 -p "Automatic restart in 10s. Restart now? (y/n): " answer

answer=${answer:-y}

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    sudo reboot
fi
