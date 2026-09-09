"""Migrate known weather autostarts to one Labwc systemd bridge."""
from pathlib import Path
import re
import shutil

BRIDGE = '"$HOME/pi-weather/desktop-start.sh" & # pi-weather'


def weather_start(line):
    if line.lstrip().startswith('#'):
        return False
    return bool(re.search(r'(?:^|[/\s"\'])start-weather\.sh(?:[\s"\'&]|$)', line)
                or 'pi-weather/desktop-start.sh' in line
                or ('chromium' in line and ('pi-weather' in line or '127.0.0.1:8765' in line))
                or ('systemctl' in line and 'start' in line and 'pi-weather-kiosk' in line))


def configure(home):
    target = home / '.config/labwc/autostart'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        content = target.read_text()
        backup = target.with_name('autostart.before-weather-v2')
        if not backup.exists():
            shutil.copy2(target, backup)
    else:
        default = Path('/etc/xdg/labwc/autostart')
        content = default.read_text() if default.exists() else ''
    lines = [line for line in content.splitlines() if not weather_start(line)]
    target.write_text('\n'.join(lines).rstrip() + '\n' + BRIDGE + '\n')
    # Disable only competing weather .desktop entries; retain a reversible copy.
    for desktop in (home / '.config/autostart').glob('*.desktop'):
        content = desktop.read_text()
        if any(line.startswith('Exec=') and weather_start(line[5:]) for line in content.splitlines()):
            backup = desktop.with_suffix('.desktop.before-weather-v2')
            if not backup.exists():
                shutil.copy2(desktop, backup)
            lines = [line for line in content.splitlines() if not line.startswith('Hidden=')]
            index = lines.index('[Desktop Entry]') + 1
            lines.insert(index, 'Hidden=true')
            desktop.write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    configure(Path.home())
