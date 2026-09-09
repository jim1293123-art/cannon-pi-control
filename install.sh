#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -ne 0 && $(id -un) == cannon ]] || {
    echo 'Log in as cannon and run this installer without sudo.' >&2; exit 1;
}
[[ -f /etc/rpi-issue ]] || { echo 'Raspberry Pi OS Desktop is required.' >&2; exit 1; }
command -v labwc >/dev/null || { echo 'Use Raspberry Pi OS Desktop with the labwc Wayland desktop.' >&2; exit 1; }
systemctl --user show-environment >/dev/null || { echo 'Log in directly as cannon so the systemd user session is available.' >&2; exit 1; }
APP_DIR="$HOME/pi-weather"
BASE='https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main'
sudo apt-get update
sudo apt-get install -y chromium curl python3 wlr-randr util-linux ca-certificates
mkdir -p "$APP_DIR" "$HOME/.config/systemd/user" "$HOME/.config/labwc"
stage=$(mktemp -d "$APP_DIR/.install.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
files=(weather.html update.sh validate_weather.py server.py kiosk.sh desktop-start.sh)
units=(pi-weather-update.service pi-weather-update.timer pi-weather-server.service pi-weather-kiosk.service)
for file in "${files[@]}"; do
    curl -fsSL --proto '=https' --proto-redir '=https' --retry 3 --connect-timeout 10 --max-time 60 "$BASE/$file" -o "$stage/$file"
    [[ -s "$stage/$file" ]]
done
for unit in "${units[@]}"; do
    curl -fsSL --proto '=https' --proto-redir '=https' --retry 3 --connect-timeout 10 --max-time 60 "$BASE/systemd/$unit" -o "$stage/$unit"
    [[ -s "$stage/$unit" ]]
done
python3 "$stage/validate_weather.py" "$stage/weather.html"
for script in update.sh kiosk.sh desktop-start.sh; do bash -n "$stage/$script"; done
# Serialize installation with the timer; do not replace a live download mid-run.
exec 9>"$APP_DIR/.update.lock"
flock 9
for file in "${files[@]}"; do
    chmod 644 "$stage/$file"
    [[ $file != *.sh ]] || chmod 755 "$stage/$file"
    mv -f -- "$stage/$file" "$APP_DIR/$file"
done
for unit in "${units[@]}"; do install -m 644 "$stage/$unit" "$HOME/.config/systemd/user/$unit"; done
flock -u 9
# Preserve the distribution autostart when creating a user override.
autostart="$HOME/.config/labwc/autostart"
if [[ ! -f $autostart ]]; then
    if [[ -f /etc/xdg/labwc/autostart ]]; then cp /etc/xdg/labwc/autostart "$autostart"; else touch "$autostart"; fi
fi
# shellcheck disable=SC2016 # HOME must expand when the desktop runs this line.
line='"$HOME/pi-weather/desktop-start.sh" & # pi-weather'
grep -Fqx "$line" "$autostart" || printf '\n%s\n' "$line" >> "$autostart"
# OS-level configuration is the only other privileged operation.
sudo raspi-config nonint do_boot_behaviour B4
sudo raspi-config nonint do_blanking 1
systemctl --user daemon-reload
systemctl --user enable --now pi-weather-server.service pi-weather-update.timer
systemctl --user restart pi-weather-server.service
if [[ -n ${WAYLAND_DISPLAY:-} ]]; then
    systemctl --user stop pi-weather-kiosk.service
    "$APP_DIR/desktop-start.sh"
fi
echo 'Installed in ~/pi-weather. Reboot to apply desktop autologin and disable screen blanking.'
echo 'Run: sudo reboot'
