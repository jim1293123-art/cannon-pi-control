#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -ne 0 ]] || exit 1
[[ ! -f "$HOME/pi-weather/.display-disabled" ]] || exit 0
# Called by the desktop, so systemd receives the real compositor environment.
[[ -n ${WAYLAND_DISPLAY:-} ]] || { echo 'A Wayland desktop session is required.' >&2; exit 1; }
systemctl --user import-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR
for variable in DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_SESSION_TYPE; do
    if [[ -n ${!variable:-} ]]; then systemctl --user import-environment "$variable"; fi
done
systemctl --user start pi-weather-server.service pi-weather-kiosk.service
