#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -ne 0 && $(id -un) == cannon ]] || {
    echo 'Log in as cannon and run this installer without sudo.' >&2; exit 1;
}
[[ -f /etc/rpi-issue ]] || { echo 'Raspberry Pi OS Desktop is required.' >&2; exit 1; }
command -v labwc >/dev/null || { echo 'Use Raspberry Pi OS Desktop with labwc / Wayland.' >&2; exit 1; }
systemctl --user show-environment >/dev/null || { echo 'Log in directly as cannon.' >&2; exit 1; }
APP_DIR="$HOME/pi-weather"
BASE='https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main'
first_install=true
[[ ! -f "$APP_DIR/kiosk.sh" ]] || first_install=false
# Existing installations keep their OS and compositor configuration.
if ! command -v chromium >/dev/null || ! command -v wlr-randr >/dev/null || ! command -v python3 >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y chromium curl python3 wlr-randr util-linux ca-certificates
fi
mkdir -p "$APP_DIR"
stage=$(mktemp -d "$APP_DIR/.bootstrap.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
for file in release_update.py validate_weather.py; do
    curl -fsSL --proto '=https' --proto-redir '=https' --retry 3 --connect-timeout 10 --max-time 60 "$BASE/$file" -o "$stage/$file"
    [[ -s "$stage/$file" ]]
done
# The new validator is loaded from staging; the installed v1 validator is older.
python3 "$stage/release_update.py" --install
python3 "$APP_DIR/configure_startup.py"
# Never rewrite an existing rotation setting, including cannon's working 270.
if [[ ! -e "$APP_DIR/rotation" ]]; then printf '270\n' > "$APP_DIR/rotation"; fi
if $first_install; then
    sudo raspi-config nonint do_boot_behaviour B4
    sudo raspi-config nonint do_blanking 1
fi
systemctl --user daemon-reload
systemctl --user enable --now pi-weather-server.service pi-weather-update.timer
systemctl --user restart pi-weather-server.service
if [[ -n ${WAYLAND_DISPLAY:-} ]]; then
    systemctl --user stop pi-weather-kiosk.service
    "$APP_DIR/desktop-start.sh"
else
    systemctl --user try-restart pi-weather-kiosk.service
fi
echo 'Weather v2 installed. Rotation and Chromium profile preserved.'
echo 'Reboot once to end any legacy duplicate browser and verify desktop startup: sudo reboot'
