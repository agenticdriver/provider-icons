#!/usr/bin/env python3
"""Import every static LobeHub SVG at an immutable revision, preserving local art."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.request

from build import ROOT, inline

REPOSITORY = 'https://github.com/lobehub/lobe-icons'
SOURCE = ROOT / 'sources/lobehub.json'
VARIANTS = {'': ('icon', 'monochrome'), '-color': ('icon', 'color'),
            '-brand': ('brand', 'monochrome'), '-brand-color': ('brand', 'color'),
            '-text': ('text', 'monochrome'), '-text-color': ('text', 'color'),
            '-text-cn': ('text-cn', 'monochrome')}


def download(url, limit=8_000_000):
    request = urllib.request.Request(url, headers={'User-Agent': 'agenticdriver-provider-icons'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'Oversized response: {url}')
    return data


def blob_hash(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def plan(toc, files):
    """Account for every source SVG; reject incomplete or changed upstream formats."""
    icons, assigned = {}, set()
    for entry in toc:
        key = entry['id'].lower()
        if not re.fullmatch(r'[a-z0-9]+', key) or key in icons:
            raise ValueError(f'Invalid or duplicate LobeHub ID: {key}')
        artworks = {}
        for suffix, (artwork, style) in VARIANTS.items():
            name = f'{key}{suffix}.svg'
            if name in files:
                artworks.setdefault(artwork, {})[style] = name
                assigned.add(name)
        if 'monochrome' not in artworks.get('icon', {}):
            raise ValueError(f'Missing base icon: {key}')
        if any('monochrome' not in styles for styles in artworks.values()):
            raise ValueError(f'Artwork without monochrome base: {key}')
        icons[key] = {'name': entry['title'], 'artworks': artworks}
    if assigned != set(files):
        raise ValueError(f'Uncatalogued SVGs: {sorted(set(files) - assigned)}')
    return dict(sorted(icons.items()))


def sync(ref, latest=False):
    previous = json.loads(SOURCE.read_text()) if SOURCE.exists() else {}
    if latest:
        commit = json.loads(download('https://api.github.com/repos/lobehub/lobe-icons/commits/master'))['sha']
    else:
        commit = ref or previous.get('commit')
    if not commit or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Supply --ref with a full commit SHA, or --latest')
    raw = f'https://raw.githubusercontent.com/lobehub/lobe-icons/{commit}'
    tree = json.loads(download(f'https://api.github.com/repos/lobehub/lobe-icons/git/trees/{commit}?recursive=1'))
    if tree.get('truncated'):
        raise ValueError('Incomplete upstream tree')
    files = {Path(item['path']).name: item['sha'] for item in tree['tree']
             if item['path'].startswith('packages/static-svg/icons/') and item['path'].endswith('.svg')}
    toc_data = download(f'{raw}/src/toc.json')
    icons = plan(json.loads(toc_data), files)
    pr_source = ROOT / 'sources/lobehub-prs.json'
    if pr_source.exists():
        additions = {id for pr in json.loads(pr_source.read_text())['pullRequests']
                     for id, entry in pr['icons'].items() if not entry.get('metadataOnly')}
        if additions & icons.keys():
            raise ValueError(f'PR artwork now exists upstream; reconcile its reviewed source before syncing: {sorted(additions & icons.keys())}')

    # The static npm archive is a fast cache only. Each SVG is verified against the
    # pinned Git tree; unreleased fixes are downloaded from that exact revision.
    package = json.loads(download(f'{raw}/packages/static-svg/package.json'))
    version = package['version']
    archive_url = f'https://registry.npmjs.org/@lobehub/icons-static-svg/-/icons-static-svg-{version}.tgz'
    cache = {}
    with tarfile.open(fileobj=io.BytesIO(download(archive_url)), mode='r:gz') as archive:
        for member in archive:
            if member.name.startswith('package/icons/') and member.name.endswith('.svg'):
                name = member.name.removeprefix('package/icons/')
                if name not in files or not member.isfile() or member.size > 2_000_000:
                    raise ValueError(f'Unexpected archive member: {member.name}')
                data = archive.extractfile(member).read()
                if blob_hash(data) == files[name]:
                    cache[name] = data

    def fetch(name):
        data = cache.get(name)
        if data is None:
            data = download(f'{raw}/packages/static-svg/icons/{name}', 2_000_000)
        if blob_hash(data) != files[name]:
            raise ValueError(f'Upstream hash mismatch: {name}')
        inline(data.decode())  # Check the complete import before writing anything.
        return name, data

    with ThreadPoolExecutor(max_workers=8) as pool:
        data = dict(pool.map(fetch, sorted(files)))
    provenance_path = ROOT / 'provenance.json'
    provenance = json.loads(provenance_path.read_text())
    managed = provenance.get('lobehub', {}).get('files', {})
    additions, updates, hashes = 0, 0, dict(managed)
    for name, content in data.items():
        target = ROOT / 'assets' / name
        if name in managed:
            if hashlib.sha256(target.read_bytes()).hexdigest() != managed[name]:
                raise ValueError(f'Locally modified imported asset: {name}')
        elif target.exists():
            continue  # Preserve the original collection and its provenance.
        digest = hashlib.sha256(content).hexdigest()
        if not target.exists():
            additions += 1
        elif target.read_bytes() != content:
            updates += 1
        hashes[name] = digest
    # All downloads and local-edit checks succeeded; now apply the import.
    for name, content in data.items():
        if name in hashes:
            (ROOT / 'assets' / name).write_bytes(content)
    snapshot = {'repository': REPOSITORY, 'commit': commit,
                'tocSha256': hashlib.sha256(toc_data).hexdigest(), 'icons': icons}
    # Retain older source entries if upstream retires an icon or an artwork.
    for key, entry in previous.get('icons', {}).items():
        if key not in icons:
            snapshot['icons'][key] = entry
        else:
            for artwork, styles in entry['artworks'].items():
                for style, file in styles.items():
                    snapshot['icons'][key]['artworks'].setdefault(artwork, {}).setdefault(style, file)
    SOURCE.parent.mkdir(exist_ok=True)
    SOURCE.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + '\n')
    provenance['lobehub'] = {'repository': REPOSITORY, 'commit': commit,
                            'path': 'packages/static-svg/icons', 'files': dict(sorted(hashes.items()))}
    provenance_path.write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'LobeHub {commit}: {len(icons)} icons, {len(files)} SVGs; {additions} added, {updates} updated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    refs = parser.add_mutually_exclusive_group()
    refs.add_argument('--ref', help='Full upstream Git commit SHA (defaults to the recorded revision)')
    refs.add_argument('--latest', action='store_true', help='Resolve upstream master once, then pin its SHA')
    args = parser.parse_args()
    sync(args.ref, args.latest)
