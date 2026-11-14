#!/usr/bin/env bash
# =====================================================================
# setup_mediamtx.sh - install MediaMTX on a Raspberry Pi 5 and stream
# both cameras over WebRTC + RTSP.
#
#   Day camera:  http://<pi>:8889/cam   rtsp://<pi>:8554/cam   (camera 1, imx708)
#   IR camera:   http://<pi>:8889/ir    rtsp://<pi>:8554/ir    (camera 0, imx219)
#
# The settings live in mediamtx.yml, next to this script; it gets installed to
# /usr/local/etc/mediamtx.yml. Keep the two files together (e.g. git clone the
# repo on the Pi, or copy the whole pi/ folder).
#
# Run on the Pi:   sudo bash setup_mediamtx.sh
# Safe to run again: it updates MediaMTX and rewrites the config
# (the old config is backed up first).
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CONF="$HERE/mediamtx.yml"
BIN=/usr/local/bin/mediamtx
CONF=/usr/local/etc/mediamtx.yml
SERVICE=/etc/systemd/system/mediamtx.service

# ---- checks -----------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo:  sudo bash $0"
  exit 1
fi
if [ "$(uname -m)" != "aarch64" ]; then
  echo "Warning: this is $(uname -m), not aarch64 (64-bit Pi OS). The arm64 download may not run."
fi
if [ ! -f "$SOURCE_CONF" ]; then
  echo "Can't find $SOURCE_CONF. Copy mediamtx.yml into the same folder as this script."
  exit 1
fi
for tool in curl tar; do
  command -v "$tool" >/dev/null || { echo "Missing $tool. Install it with: sudo apt install -y $tool"; exit 1; }
done

# ---- 1. download the latest MediaMTX release for 64-bit ARM ------------
echo "Finding the latest MediaMTX release..."
# Release files are named ..._linux_arm64.tar.gz (older releases: _linux_arm64v8)
URL=$(curl -fsSL https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
  | grep -oE '"browser_download_url": *"[^"]*_linux_arm64(v8)?\.tar\.gz"' \
  | head -n 1 | sed -E 's/.*"(https[^"]+)"/\1/')
if [ -z "$URL" ]; then
  echo "Couldn't find the download link. Check the internet connection, or download it by hand from"
  echo "https://github.com/bluenviron/mediamtx/releases"
  exit 1
fi
echo "Downloading $URL"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP/mediamtx.tar.gz"
tar -xzf "$TMP/mediamtx.tar.gz" -C "$TMP"

# ---- 2. install the program ------------------------------------------
systemctl stop mediamtx 2>/dev/null || true   # in case an older copy is running
install -m 755 "$TMP/mediamtx" "$BIN"
echo "Installed $($BIN --version 2>/dev/null || echo mediamtx) to $BIN"

# ---- 3. write the config ---------------------------------------------
mkdir -p "$(dirname "$CONF")"
if [ -f "$CONF" ]; then
  cp "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"
  echo "Backed up the old config next to $CONF"
fi
install -m 644 "$SOURCE_CONF" "$CONF"
echo "Installed $SOURCE_CONF -> $CONF"

# ---- 4. run it as a service (starts on boot, restarts if it crashes) --
cat > "$SERVICE" <<EOF
[Unit]
Description=MediaMTX camera server (Day + IR)
Wants=network-online.target
After=network-online.target

[Service]
ExecStart=$BIN $CONF
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable mediamtx >/dev/null
systemctl restart mediamtx
sleep 2

# ---- done ------------------------------------------------------------
if systemctl is-active --quiet mediamtx; then
  echo
  echo "MediaMTX is running. Open from the laptop (same Wi-Fi / hotspot):"
  for ip in $(hostname -I); do
    case "$ip" in *:*) continue ;; esac   # skip IPv6, show IPv4 only
    echo "  Day: http://$ip:8889/cam    IR: http://$ip:8889/ir"
  done
  echo "  (or http://$(hostname).local:8889/cam)"
  echo "Logs: journalctl -u mediamtx -f"
else
  echo "MediaMTX didn't start. See why with:  journalctl -u mediamtx -n 50 --no-pager"
  exit 1
fi
