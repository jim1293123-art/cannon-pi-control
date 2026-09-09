"""Unprivileged, manifest-verified updates with rollback and persistent recovery.

Only allowlisted application files are managed. Rotation, browser profile and
local display preferences are deliberately outside the release.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.request import urlopen

from validate_weather import validate

BASE = 'https://raw.githubusercontent.com/jim1293123-art/cannon-pi-control/main'
RUNTIME = ('weather.html', 'server.py', 'kiosk.sh', 'desktop-start.sh', 'update.sh',
           'release_update.py', 'validate_weather.py', 'configure_startup.py')
UNITS = ('pi-weather-kiosk.service', 'pi-weather-server.service',
         'pi-weather-update.service', 'pi-weather-update.timer')
FILES = RUNTIME + tuple('systemd/' + name for name in UNITS)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(name, stamp):
    # curl restricts both the original URL and redirects to HTTPS.
    result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                             '--proto', '=https', '--proto-redir', '=https',
                             '--connect-timeout', '10', '--max-time', '15',
                             '--max-filesize', '2000000', f'{BASE}/{name}?release={stamp}'],
                            check=True, capture_output=True, timeout=20)
    return result.stdout


def parse_manifest(raw):
    value = json.loads(raw)
    if value.get('schema') != 1 or set(value.get('files', {})) != set(FILES):
        raise ValueError('Unexpected release schema or file list')
    if not all(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v)
               for v in value['files'].values()):
        raise ValueError('Invalid release checksum')
    return value


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.weather-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def systemctl(*args):
    subprocess.run(['systemctl', '--user', *args], check=True, timeout=30)


def check_server():
    for _ in range(30):
        try:
            with urlopen('http://127.0.0.1:8765/health', timeout=1) as response:
                if json.load(response).get('version') == 2:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.3)
    raise RuntimeError('Updated server failed its health check')


def destinations(home):
    return {name: home / ('.config/systemd/user/' + name[8:] if name.startswith('systemd/')
                         else 'pi-weather/' + name) for name in FILES}


def validate_release(stage):
    validate(stage / 'weather.html')
    for name in RUNTIME:
        content = (stage / name).read_text(encoding='utf-8')
        if name.endswith('.py'):
            ast.parse(content)
        if name.endswith('.sh'):
            subprocess.run(['bash', '-n', str(stage / name)], check=True, capture_output=True)
    kiosk = (stage / 'kiosk.sh').read_text()
    if '--password-store=basic' not in kiosk or '$HOME/pi-weather/rotation' not in kiosk:
        raise ValueError('Release lost the password store or local rotation setting')
    if 'rotation=90' in kiosk or '--no-sandbox' in kiosk:
        raise ValueError('Release violates kiosk configuration')
    bridge = (stage / 'desktop-start.sh').read_text()
    if 'chromium' in bridge or 'start-weather.sh' in bridge:
        raise ValueError('Desktop bridge must only start systemd units')
    for name in UNITS:
        text = (stage / 'systemd' / name).read_text()
        if '[Unit]' not in text or ('[Timer]' if name.endswith('.timer') else '[Service]') not in text:
            raise ValueError('Invalid systemd unit: ' + name)
        if re.search(r'(?m)^User=root\s*$', text) or 'sudo ' in text:
            raise ValueError('Updates must remain unprivileged')


def recover(home, targets):
    """Restore a previous transaction after a failure or interrupted update."""
    app = home / 'pi-weather'
    pending = app / '.update-pending.json'
    if not pending.exists():
        return
    state = json.loads(pending.read_text())
    if not set(state) <= set(FILES):
        raise ValueError('Unexpected recovery paths')
    for name, mode in state.items():
        if mode is None:
            targets[name].unlink(missing_ok=True)
        else:
            atomic_write(targets[name], (app / '.update-backup' / name).read_bytes(), mode)
    systemctl('daemon-reload')
    # try-restart never opens a kiosk which Exit to Desktop has stopped.
    systemctl('try-restart', 'pi-weather-server.service')
    systemctl('try-restart', 'pi-weather-kiosk.service')
    pending.unlink()


def apply_release(home, download=fetch, installing=False):
    app = home / 'pi-weather'
    app.mkdir(parents=True, exist_ok=True)
    targets = destinations(home)
    recover(home, targets)
    raw = download('release.json', int(time.time()))
    manifest = parse_manifest(raw)
    changed = [name for name in FILES if not targets[name].is_file()
               or digest(targets[name].read_bytes()) != manifest['files'][name]]
    if not changed:
        print('Weather release already current.')
        return
    with tempfile.TemporaryDirectory(prefix='.release-', dir=app) as directory:
        stage = Path(directory)
        # All files must match the same manifest before any live file changes.
        # If main changes during download, checksum mismatch defers to next run.
        for name in FILES:
            content = download(name, digest(raw))
            if not content or digest(content) != manifest['files'][name]:
                raise ValueError('Release checksum mismatch: ' + name)
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        validate_release(stage)
        state = {}
        for name in changed:
            path = targets[name]
            state[name] = path.stat().st_mode & 0o777 if path.exists() else None
            if path.exists():
                atomic_write(app / '.update-backup' / name, path.read_bytes())
        pending = app / '.update-pending.json'
        atomic_write(pending, json.dumps(state).encode())
        try:
            for name in changed:
                atomic_write(targets[name], (stage / name).read_bytes(),
                             0o755 if name.endswith('.sh') else 0o644)
            if any(name.startswith('systemd/') for name in changed):
                systemctl('daemon-reload')
            if not installing:
                if 'server.py' in changed or 'systemd/pi-weather-server.service' in changed:
                    systemctl('restart', 'pi-weather-server.service')
                    check_server()
                if 'kiosk.sh' in changed or 'systemd/pi-weather-kiosk.service' in changed:
                    systemctl('try-restart', 'pi-weather-kiosk.service')
                if 'systemd/pi-weather-update.timer' in changed:
                    systemctl('try-restart', 'pi-weather-update.timer')
            atomic_write(app / '.installed-release.json', raw)
            pending.unlink()
        except Exception:
            recover(home, targets)
            raise
    print('Installed weather release: ' + ', '.join(changed))


def main():
    if os.geteuid() == 0:
        raise SystemExit('Run as cannon, not root.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    import fcntl
    app = Path.home() / 'pi-weather'
    app.mkdir(parents=True, exist_ok=True)
    with (app / '.update.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if args.install:
                fcntl.flock(lock, fcntl.LOCK_EX)
            else:
                return
        apply_release(Path.home(), installing=args.install)


if __name__ == '__main__':
    main()
