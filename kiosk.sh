#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo 'Run as cannon, not root.' >&2; exit 1; }
[[ -n ${WAYLAND_DISPLAY:-} ]] || { echo 'Start from the Wayland desktop.' >&2; exit 1; }
rotation=270
if [[ -f "$HOME/pi-weather/rotation" ]]; then read -r rotation < "$HOME/pi-weather/rotation"; fi
[[ $rotation == 90 || $rotation == 270 ]] || { echo 'rotation must be 90 or 270' >&2; exit 1; }
# Touch Display 2 is natively 720x1280. Rotate its DSI output, keeping scale 1.
output=''
for _ in {1..20}; do
    output=$(wlr-randr | awk '/^DSI-[0-9]+ / {print $1; exit}')
    [[ -z $output ]] || break
    sleep 1
done
[[ -n $output ]] || { echo 'Touch Display DSI output not found; run wlr-randr.' >&2; exit 1; }
wlr-randr --output "$output" --on --preferred --transform "$rotation" --scale 1 --pos 0,0
ready=false
for _ in {1..30}; do
    if curl -fsS --max-time 2 http://127.0.0.1:8765/revision >/dev/null; then ready=true; break; fi
    sleep 1
done
$ready || { echo 'Local weather server did not become ready.' >&2; exit 1; }
browser=$(command -v chromium || command -v chromium-browser)
exec "$browser" --ozone-platform=wayland --kiosk --start-fullscreen \
    --window-position=0,0 --window-size=1280,720 --force-device-scale-factor=1 \
    --no-first-run --noerrdialogs --disable-session-crashed-bubble --password-store=basic \
    --user-data-dir="$HOME/pi-weather/chromium-profile" \
    http://127.0.0.1:8765/weather.html
