"""Structural download guard, not a security audit of trusted repository code."""
from html.parser import HTMLParser
from pathlib import Path
import sys


class WeatherParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = set()
        self.ids = set()
        self.marker = False

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        attrs = dict(attrs)
        self.ids.add(attrs.get('id'))
        if tag == 'meta' and attrs.get('name') == 'pi-weather-app':
            self.marker = attrs.get('content') == '2'


def validate(path):
    raw = Path(path).read_bytes()
    if not 1024 <= len(raw) <= 2_000_000:
        raise ValueError('HTML must be between 1 KB and 2 MB')
    content = raw.decode('utf-8')
    parser = WeatherParser()
    parser.feed(content)
    parser.close()
    if not parser.marker or not {'html', 'head', 'body', 'script'} <= parser.tags:
        raise ValueError('Missing weather app marker or document structure')
    if not {'app', 'homeView', 'radarView', 'forecastView', 'settingsView',
            'hourly', 'week', 'exitDesktop', 'radarFrame', 'unitSetting'} <= parser.ids:
        raise ValueError('Missing required weather UI elements')
    if not content.rstrip().lower().endswith('</html>') or '</script>' not in content.lower():
        raise ValueError('Incomplete HTML document')


if __name__ == '__main__':
    try:
        validate(sys.argv[1])
    except (ValueError, OSError, IndexError) as error:
        sys.exit(f'Weather validation failed: {error}')
