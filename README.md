# Cannon Pi Weather

Fullscreen touchscreen weather for **Raspberry Pi 5**, the official **Touch
Display 2**, and user **cannon**. `weather.html` is the complete UI, designed for
**1280×720 landscape**, with all forecast sections visible without scrolling.

## Install

Use Raspberry Pi OS **Desktop 64-bit with labwc / Wayland** (current Trixie or
updated Bookworm). Connect the Touch Display 2 and internet, log in as `cannon`,
and paste this command into a terminal **without sudo**:

```bash
bash -c 'set -e; file=$(mktemp); trap '\''rm -f "$file"'\'' EXIT; curl -fsSL --proto "=https" --proto-redir "=https" https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main/install.sh -o "$file"; bash "$file"'
```

Then run `sudo reboot`. Sudo is used only to install OS packages and configure
desktop autologin and disabled screen blanking. App files, Chromium, the server,
and the updater belong to `cannon`. No API key or GitHub credential is installed.
Raspberry Pi OS Lite and X11 sessions are not supported by this setup.

The installer creates `~/pi-weather`, installs systemd user units under
`~/.config/systemd/user`, and adds one entry to `~/.config/labwc/autostart`,
preserving existing entries. The desktop passes its Wayland environment to
systemd before launching the kiosk. A dedicated Chromium profile saves the city,
units, and last successful forecast. Reinstalling preserves those preferences.

The launcher detects the DSI output and rotates the native 720×1280 panel 90
degrees at scale 1, producing 1280×720. For the opposite landscape direction:

```bash
echo 270 > ~/pi-weather/rotation
systemctl --user restart pi-weather-kiosk.service
```

Use a dedicated, single-display kiosk. Check touch alignment after first boot;
Raspberry Pi OS Wayland handles touch with the rotated output. If needed, check
output and touch mapping in the desktop's Control Centre / Screens settings.
The launcher reapplies the selected rotation whenever it starts.

## Features

- Current temperature, weather condition, feels-like, and today's high/low.
- Humidity, this hour's rain chance, wind speed/direction, today's peak UV,
  sunrise and sunset.
- Next 12 hourly forecasts and a seven-day forecast including today.
- Tap the city name to search worldwide by city or postal code. The built-in
  touch keyboard requires no OS keyboard. Phoenix is the initial city.
- Tap the unit button for Fahrenheit/mph or Celsius/km/h. Times follow the
  selected city's timezone, including daylight saving time.
- Weather refreshes every ten minutes; failures retry every minute. Cached data
  remains visible with offline/stale labeling. Missing values appear as `--`.

Data uses [Open-Meteo](https://open-meteo.com/en/docs) and its
[geocoding API](https://open-meteo.com/en/docs/geocoding-api), with no API key.
The free API is intended for non-commercial use and has usage limits.

## Automatic updates

`pi-weather-update.timer` runs `pi-weather-update.service` about every 60 seconds
while `cannon`'s user session is running. Desktop autologin starts that session
after reboot; no root timer or user lingering is needed.

`~/pi-weather/update.sh` downloads only
[`main/weather.html`](https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main/weather.html)
over HTTPS into a temporary file beside the live file. Validation checks download
success, size, UTF-8, the app marker, required elements and document completion.
Empty, truncated, error or structurally invalid responses leave the live file
untouched. Identical content is not replaced. Changed valid content is installed
with an atomic rename, with a lock preventing overlapping installs.

Validation is a structural guard, not a security audit or a JavaScript test;
`main` is the trusted source of application code. The updater never executes
downloaded shell scripts, uses no sudo, and has `NoNewPrivileges=yes`.

The loopback server at `http://127.0.0.1:8765/weather.html` exposes only the UI and
its revision hash. The browser checks the revision every 15 seconds and reloads
on change, retaining preferences. GitHub caching or an outage can delay delivery
beyond one minute. Only `weather.html` updates automatically; rerun the installer
to upgrade supporting scripts and units.

## Stop and start

Run as `cannon`, in a terminal or SSH login as that user.

Stop the display now (it returns at next desktop login):

```bash
systemctl --user stop pi-weather-kiosk.service
```

Start again after the desktop has loaded:

```bash
systemctl --user start pi-weather-kiosk.service
```

If the environment has not yet been imported, run
`~/pi-weather/desktop-start.sh` **from a desktop terminal**. SSH alone cannot
provide a missing graphical session.

Keep the display off across reboots:

```bash
touch ~/pi-weather/.display-disabled
systemctl --user stop pi-weather-kiosk.service
```

Restore startup and start the display:

```bash
rm -f ~/pi-weather/.display-disabled
systemctl --user start pi-weather-kiosk.service
```

Pause updates with `systemctl --user disable --now pi-weather-update.timer`.
Resume with `systemctl --user enable --now pi-weather-update.timer`.

## Troubleshooting

```bash
# Health and update schedule
systemctl --user status pi-weather-server pi-weather-kiosk pi-weather-update.timer
systemctl --user list-timers pi-weather-update.timer
journalctl --user -u pi-weather-kiosk -u pi-weather-server -u pi-weather-update -n 100 --no-pager

# Force update and check installed HTML / local server
systemctl --user start pi-weather-update.service
python3 ~/pi-weather/validate_weather.py ~/pi-weather/weather.html
curl -f http://127.0.0.1:8765/revision

# Network checks
curl -I https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main/weather.html
curl -f 'https://api.open-meteo.com/v1/forecast?latitude=33.4484&longitude=-112.074&current=temperature_2m'

# Run in a desktop terminal
echo "$XDG_SESSION_TYPE $WAYLAND_DISPLAY"
wlr-randr
tail -n 10 ~/.config/labwc/autostart

# Restart display and local server
systemctl --user restart pi-weather-server.service pi-weather-kiosk.service
```

For a dark screen, check Desktop autologin and disabled screen blanking in
`sudo raspi-config`, then reboot. For a missing DSI output, check the display
cable and run `wlr-randr` in the desktop. Port-8765 conflicts appear in the server
journal; stop the conflicting process before restarting. Do not run Chromium
with sudo or add `--no-sandbox`.

Desktop startup follows the
[Raspberry Pi kiosk guide](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/).

## Development checks

```bash
python3 -m unittest discover -s tests -v
for script in *.sh; do bash -n "$script"; done
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node tests/browser.cjs
```

Automated checks cover validation, updater failure handling, server routes and
revisions, and browser layout and interactions. Physical rotation, touch
alignment, desktop startup and reboot behavior need verification on the Pi.
