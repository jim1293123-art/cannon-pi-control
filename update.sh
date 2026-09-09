#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo 'Run as cannon, not root.' >&2; exit 1; }
APP_DIR="$HOME/pi-weather"
URL='https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main/weather.html'
mkdir -p "$APP_DIR"
exec 9>"$APP_DIR/.update.lock"
flock -n 9 || exit 0
tmp=$(mktemp "$APP_DIR/.weather.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
# Cache busting requests a fresh raw resource; GitHub may still cache briefly.
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 10 --max-time 40 --max-filesize 2000000 \
    --header 'Cache-Control: no-cache' "$URL?check=$(date +%s)" -o "$tmp"
python3 "$APP_DIR/validate_weather.py" "$tmp"
if [[ -f "$APP_DIR/weather.html" ]] && cmp -s "$tmp" "$APP_DIR/weather.html"; then
    echo 'Weather UI already current.'
    exit 0
fi
chmod 644 "$tmp"
# Same-filesystem rename: interrupted/invalid downloads never touch the live file.
mv -f -- "$tmp" "$APP_DIR/weather.html"
echo 'Installed updated weather UI.'
