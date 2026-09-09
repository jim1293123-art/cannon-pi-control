"""Regenerate release.json after edits; --check is used by CI."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_update import FILES

manifest = {'schema': 1, 'files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                  for name in FILES}}
content = json.dumps(manifest, indent=2) + '\n'
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
if parser.parse_args().check:
    if (ROOT / 'release.json').read_text() != content:
        sys.exit('Run python3 tools/build_release.py and commit release.json')
else:
    (ROOT / 'release.json').write_text(content, encoding='utf-8', newline='\n')
