"""Pin prebuilt native font data to its inputs; release checks need no font tools."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    catalog = json.loads((ROOT / 'manifest.json').read_text())
    paths = ['manifest.json', 'fonts/glyphs.json', 'fonts/UsageStatProviderIcons.ttf',
             'scripts/build_font.py', 'fonts/requirements-build.txt']
    paths += sorted({'assets/' + icon['monochrome'] for icon in catalog['icons'].values()})
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def record():
    (ROOT / 'fonts/source.json').write_text(json.dumps(inputs(), indent=2) + '\n')


if __name__ == '__main__':
    if json.loads((ROOT / 'fonts/source.json').read_text()) != inputs():
        raise SystemExit('Native icon font is stale. Run npm run build:font and commit the generated font data before releasing.')
