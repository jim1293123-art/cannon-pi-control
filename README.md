# Cannon Pi Weather v2

The existing `jim1293123-art/cannon-pi-control` project, upgraded from
`Cannon-Weather-v2-Radar-Settings.zip`. Designed for Raspberry Pi 5, user `cannon`,
Touch Display 2, and **1280×720 landscape** on Raspberry Pi OS Desktop with
**Wayland / labwc**.

## One-time v2 upgrade

The old updater downloads only HTML. **Run this once as `cannon`, without sudo
in front of the command**, to install the new backend, exit action and complete
release updater:

```bash
bash -c 'set -e; file=$(mktemp); trap '\''rm -f "$file"'\'' EXIT; curl -fsSL --proto "=https" --proto-redir "=https" https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main/install.sh -o "$file"; bash "$file"'
```

Then run `sudo reboot` once. This ends any old browser process and verifies the
single startup path. The installer also works for a fresh Pi OS Desktop install.
On an existing setup it preserves OS autologin and blanking configuration; on a
fresh install it enables desktop autologin and disables screen blanking. Sudo is
used only for missing OS packages and initial OS configuration.

**Your existing `~/pi-weather/rotation` value of `270` is preserved.** The launcher
continues reading that file, never writes to it, and defaults to 270 only when
it is missing. Releases cannot contain `rotation`. Chromium keeps
`--password-store=basic` and the existing `~/pi-weather/chromium-profile`.

V2 HTML carries a new app marker: the original v1 validator intentionally leaves
v1 running until this upgrade installs all required files together.

## App

- **Home:** temperature, condition, feels-like, high/low, humidity, current-hour
  rain chance, wind speed/direction, today's peak UV, sunrise/sunset, next 12 hours,
  and seven days including today. Active US weather alerts open readable details.
- **Live Radar:** the ZIP's interactive Windy radar map, centered on the selected
  city, with pan/zoom, refresh and recenter controls. The map loads when opened
  and refreshes every five minutes while visible. Internet and regional radar
  coverage are required; use the provider's timeline to inspect observation times.
- **Details:** temperature and rain-chance graphs, daylight progress, extra daily
  readings, and US AQI / PM2.5 / PM10 when available.
- **Settings:** city/postal-code search, built-in touch keyboard, six saved
  locations, Fahrenheit/mph or Celsius/km/h, 12/24-hour time, weather refresh
  interval, manual refresh, and **Exit Weather App to Desktop**.

Settings save immediately. Existing v1 city/unit preferences are migrated where
available. Times follow the selected city's timezone. Weather defaults to a
10-minute refresh; failures retry after 60 seconds, including a failed first
request. Cached forecasts remain visible with offline/stale labels. Missing
values are shown as `--`, never a fabricated zero.

Weather: [Open-Meteo](https://open-meteo.com/en/docs); search:
[Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api); air quality:
[CAMS / Open-Meteo](https://open-meteo.com/en/docs/air-quality-api); US alerts:
[NWS](https://www.weather.gov/documentation/services-web-alerts); radar:
[Windy](https://embed.windy.com/). No API key is needed. Coverage and provider
availability vary; unavailable alerts are distinguished from no active alerts.
Open-Meteo's free service is for non-commercial use and has usage limits.

## Exit and startup

Chromium is launched **only by `pi-weather-kiosk.service`**. One Labwc
`desktop-start.sh` bridge imports the actual Wayland session environment and asks
systemd to start that service; it does not launch Chromium itself. The installer
removes known legacy `start-weather.sh`, direct weather Chromium and duplicate
bridge lines from the user's Labwc autostart. It disables matching XDG desktop
entries. Original files are backed up beside them as `*.before-weather-v2`.
Unrelated desktop startup entries are retained. The updater never edits autostart.

The local Python server binds **127.0.0.1:8765** and serves only the weather UI,
`/revision`, `/health`, and `POST /exit`. The Exit button sends a request with a
page token. The backend validates the local Host, Origin and token, then runs:

```bash
systemctl --user --no-block stop pi-weather-kiosk.service
```

Stopping the service closes only that service's Chromium process group and
suppresses automatic restart. Other Chromium windows/profiles, the weather
server and updater remain running. A backend update does not stop the browser;
a launcher update uses `try-restart`, so it does not reopen a kiosk you exited.
At the next desktop login or reboot, the kiosk starts normally.

Start it again after Exit, from a desktop terminal or SSH as `cannon`:

```bash
systemctl --user start pi-weather-kiosk.service
```

If the Wayland environment has not yet been imported, run
`~/pi-weather/desktop-start.sh` from a **desktop terminal**. An SSH login alone
cannot create the missing desktop session.

Stop now, or keep it off across future logins:

```bash
systemctl --user stop pi-weather-kiosk.service
# Optional: persistently disable desktop launch
 touch ~/pi-weather/.display-disabled
```

Re-enable persistent startup:

```bash
rm -f ~/pi-weather/.display-disabled
systemctl --user start pi-weather-kiosk.service
```

## Full-release updates

`pi-weather-update.timer` checks GitHub about every 60 seconds as `cannon`.
`update.sh` calls `release_update.py`, which fetches `release.json` from `main`.
The manifest contains SHA-256 checksums for the HTML, Python backend/updater,
validator, launchers, startup migration helper and all four systemd user units.
It cannot specify arbitrary paths, rotation, the browser profile or local flags.

On change, every required file is downloaded to staging and checked against the
same manifest. Python and shell syntax, HTML structure and key kiosk invariants
are checked before any live file is touched. Network errors, empty responses,
invalid files or a mixed-commit download leave the installation unchanged.
Application code on `main` remains trusted; checksums are consistency checks,
not independent signatures or a security audit.

Only changed files are replaced, using same-directory atomic renames under one
update lock. A backup and persistent transaction record allow rollback on a
failed install/health check or recovery at the next run after an interruption.
The backend restarts and passes `/health` when changed; units trigger a user
`daemon-reload`. The browser detects HTML changes through `/revision` every 15
seconds. All of this is unprivileged, with `NoNewPrivileges=yes`; the updater
never invokes sudo. Supporting files update automatically after the one-time
v2 migration. The installer itself is only run explicitly.

To publish future changes, edit the repository, run
`python3 tools/build_release.py`, and commit **release.json with the changed
files**. CI rejects an out-of-date manifest. GitHub caches or an outage may delay
an update beyond one minute.

Pause/resume updates:

```bash
systemctl --user disable --now pi-weather-update.timer
systemctl --user enable --now pi-weather-update.timer
```

## Troubleshooting

Run as `cannon`:

```bash
cat ~/pi-weather/rotation
systemctl --user status pi-weather-server pi-weather-kiosk pi-weather-update.timer
systemctl --user list-timers pi-weather-update.timer
journalctl --user -u pi-weather-server -u pi-weather-kiosk -u pi-weather-update -n 100 --no-pager
curl -f http://127.0.0.1:8765/health
curl -f http://127.0.0.1:8765/revision
systemctl --user start pi-weather-update.service
python3 ~/pi-weather/validate_weather.py ~/pi-weather/weather.html
systemctl --user restart pi-weather-server.service
systemctl --user start pi-weather-kiosk.service
```

`/health` should report version 2 and exit support. If Exit reports the backend
is unavailable, run the one-time installer above and inspect the server journal.
Do not use `pkill chromium`, sudo Chromium or `--no-sandbox` as an exit workaround.

In a desktop terminal, check startup and the display:

```bash
echo "$XDG_SESSION_TYPE $WAYLAND_DISPLAY"
wlr-randr
cat ~/.config/labwc/autostart
pgrep -af 'chromium.*pi-weather/chromium-profile'
```

Several Chromium subprocesses in the service are normal; a separate direct
`start-weather.sh` browser is not. Reboot after migration to end any legacy
process. If the output is missing, inspect the DSI cable and desktop Screens
settings. This setup retains the existing `rotation` mechanism and expects a
single Touch Display 2. Port 8765 must be available.

## Validation

```bash
python3 tools/build_release.py --check
python3 -m unittest discover -s tests -v
for script in *.sh; do bash -n "$script"; done
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node tests/browser.cjs
```

Tests cover all tabs at 1280×720, settings, touch search, timezone handling,
offline retries, revision reload, the exit POST and exact service target,
startup migration, failed/mixed releases, rollback and protected local settings.
The Linux launcher test simulates a DSI display and verifies 270, the dedicated
profile and `--password-store=basic`. Actual Pi reboot, physical touch alignment
and service/window behavior still need verification on the device.
