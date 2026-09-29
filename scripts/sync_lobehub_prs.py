#!/usr/bin/env python3
"""Replay reviewed PR artwork, or snapshot explicitly selected LobeHub PRs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from build import ROOT, inline
from sync_lobehub import blob_hash, download

SOURCE = ROOT / 'sources/lobehub-prs.json'
VARIANTS = {
    'Mono': ('', 'icon', 'monochrome'), 'Color': ('-color', 'icon', 'color'),
    'Text': ('-text', 'text', 'monochrome'), 'TextColor': ('-text-color', 'text', 'color'),
    'Brand': ('-brand', 'brand', 'monochrome'), 'BrandColor': ('-brand-color', 'brand', 'color'),
    'TextCn': ('-text-cn', 'text-cn', 'monochrome'),
}


def github(endpoint, paginate=False):
    command = ['gh', 'api', endpoint]
    if paginate:
        command += ['--paginate', '--slurp']
    result = json.loads(subprocess.check_output(command, text=True))
    return [item for page in result for item in page] if paginate else result


def snapshot_pr(number):
    endpoint = f'repos/lobehub/lobe-icons/pulls/{number}'
    pr = github(endpoint)
    files = github(endpoint + '/files?per_page=100', paginate=True)
    repository, commit = pr['head']['repo']['full_name'], pr['head']['sha']
    selected = [item for item in files if item['status'] != 'removed' and
                (re.fullmatch(r'src/[A-Z][A-Za-z0-9]+/(?:style\.ts|components/[A-Za-z0-9]+\.tsx)', item['filename']) or
                 re.fullmatch(r'packages/static-svg/icons/[a-z0-9-]+\.svg', item['filename']))]
    if not selected:
        raise ValueError(f'PR #{number} contains no supported icon artwork or metadata')

    def read(item):
        data = download(f'https://raw.githubusercontent.com/{repository}/{commit}/{item["filename"]}', 2_000_000)
        if blob_hash(data) != item['sha']:
            raise ValueError(f'PR changed while reading: {item["filename"]}; retry with a stable head')
        return item['filename'], {'content': data.decode(), 'gitBlob': item['sha'],
                                  'sha256': hashlib.sha256(data).hexdigest()}

    with ThreadPoolExecutor(8) as pool:
        sources = dict(sorted(pool.map(read, selected)))
    if github(endpoint)['head']['sha'] != commit:
        raise ValueError(f'PR #{number} changed while reading; retry')
    return {'number': number, 'url': pr['html_url'], 'title': pr['title'],
            'stateAtReview': 'merged' if pr['merged_at'] else pr['state'],
            'repository': repository, 'commit': commit, 'files': sources}


def verified_files(pr):
    if not re.fullmatch(r'[0-9a-f]{40}', pr['commit']):
        raise ValueError('PR sources require a full commit SHA')
    contents = {}
    for path, source in pr['files'].items():
        if not re.fullmatch(r'(?:src/[A-Z][A-Za-z0-9]+/(?:style\.ts|components/[A-Za-z0-9]+\.tsx)|packages/static-svg/icons/[a-z0-9-]+\.svg)', path):
            raise ValueError(f'Unexpected PR source path: {path}')
        data = source['content'].encode()
        if hashlib.sha256(data).hexdigest() != source['sha256'] or blob_hash(data) != source['gitBlob']:
            raise ValueError(f'PR source digest mismatch: #{pr["number"]} {path}')
        contents[path] = source['content']
    return contents


def adjust_geometry(data, adjustment):
    """Apply explicitly reviewed framing/orientation corrections, never new paths."""
    if set(adjustment) - {'viewBox', 'flipY', 'reason', 'sourceSha256'} or not adjustment.get('reason', '').strip():
        raise ValueError('Geometry adjustments need a reason and supported fields')
    root = ET.fromstring(data)
    if 'viewBox' in adjustment:
        values = [float(value) for value in adjustment['viewBox'].split()]
        if len(values) != 4 or not all(math.isfinite(value) for value in values) or min(values[2:]) <= 0:
            raise ValueError('Invalid adjusted viewBox')
        root.set('viewBox', adjustment['viewBox'])
    if 'flipY' in adjustment:
        height = adjustment['flipY']
        if not isinstance(height, (float, int)) or not math.isfinite(height) or height <= 0:
            raise ValueError('Invalid wordmark flip')
        group = ET.Element('{http://www.w3.org/2000/svg}g', {'transform': f'translate(0 {height}) scale(1 -1)'})
        for child in list(root):
            if child.tag != '{http://www.w3.org/2000/svg}title':
                root.remove(child)
                group.append(child)
        root.append(group)
    return (ET.tostring(root, encoding='unicode') + '\n').encode()


def generate(snapshot):
    assets, requests, targets = {}, [], []
    base = json.loads((ROOT / 'sources/lobehub.json').read_text())['icons']
    seen, seen_prs = set(), set()
    for pr in snapshot['pullRequests']:
        if pr['number'] in seen_prs:
            raise ValueError(f'Duplicate PR #{pr["number"]}')
        seen_prs.add(pr['number'])
        files = verified_files(pr)
        pr['icons'], pr['artworkSources'] = {}, {}
        folders = sorted(Path(path).parent.name for path in files if path.endswith('/style.ts'))
        if not folders:
            raise ValueError(f'PR #{pr["number"]} has no literal icon metadata')
        omitted = pr.get('omitted', {})
        if not set(omitted) <= set(files) or any(not reason.strip() for reason in omitted.values()):
            raise ValueError('Every omitted source must be present and have a review reason')
        for folder in folders:
            key = folder.lower()
            if key in seen:
                raise ValueError(f'Multiple PRs modify {key}; reconcile their source first')
            seen.add(key)
            title = re.search(r"export const TITLE = (['\"])(.*?)\1;", files[f'src/{folder}/style.ts'])
            if not title:
                raise ValueError(f'Missing literal TITLE: {folder}')
            entry = {'name': title[2], 'componentName': folder, 'artworks': {}}
            for component, (suffix, artwork, style) in VARIANTS.items():
                name = f'{key}{suffix}.svg'
                static = f'packages/static-svg/icons/{name}'
                tsx = f'src/{folder}/components/{component}.tsx'
                path = static if static in files else tsx
                if path not in files or path in omitted:
                    continue
                if key in base:
                    raise ValueError(f'{key} already exists in reviewed upstream; reconcile artwork sources before importing this PR')
                entry['artworks'].setdefault(artwork, {})[style] = name
                record = {'path': path, 'format': 'svg' if path == static else 'tsx'}
                pr['artworkSources'][name] = record
                if path == static:
                    assets[name] = files[path].encode()
                    record['sources'] = [path]
                else:
                    requests.append({'files': files, 'entry': path, 'componentName': folder})
                    targets.append((name, record))
            if not entry['artworks']:
                if key not in base:
                    raise ValueError(f'Missing artwork: {key}')
                del entry['artworks']
                entry['metadataOnly'] = True
            elif any('monochrome' not in styles for styles in entry['artworks'].values()) or 'icon' not in entry['artworks']:
                raise ValueError(f'Missing monochrome base: {key}')
            pr['icons'][key] = entry
        accounted = {record['path'] for record in pr['artworkSources'].values()} | set(omitted)
        for path in files:
            if path.startswith('packages/static-svg/') and path not in accounted:
                raise ValueError(f'Uncatalogued static SVG in PR #{pr["number"]}: {path}')
            match = re.fullmatch(r'src/[^/]+/components/(.+)\.tsx', path)
            if match and match[1] not in {*VARIANTS, 'Avatar', 'Combine', 'Inner', 'Logo'}:
                raise ValueError(f'Unknown artwork component: {path}')

    if requests:
        result = subprocess.run(['node', str(ROOT / 'scripts/extract_lobehub_tsx.mjs')],
                                input=json.dumps(requests), text=True, capture_output=True, check=False)
        if result.returncode:
            raise ValueError(result.stderr.strip())
        converted = json.loads(result.stdout)
        if len(converted) != len(targets):
            raise ValueError('Incomplete TSX extraction')
        for (name, record), output in zip(targets, converted):
            assets[name] = output['svg'].encode()
            record['sources'] = output['sources']
    for pr in snapshot['pullRequests']:
        for name, adjustment in pr.get('adjustments', {}).items():
            source = pr['artworkSources'].get(name)
            if not source or source['format'] != 'tsx' or adjustment.get('sourceSha256') != pr['files'][source['path']]['sha256']:
                raise ValueError(f'Geometry correction must match the reviewed TSX source: {name}')
            assets[name] = adjust_geometry(assets[name], adjustment)
    for name, data in assets.items():
        inline(data.decode())  # Reject active content and unknown rendering features before any writes.
    return assets


def sync(add=(), omissions=(), check=False):
    snapshot = json.loads(SOURCE.read_text()) if SOURCE.exists() else {'version': 1, 'pullRequests': []}
    for number in add:
        pr = snapshot_pr(number)
        previous = next((entry for entry in snapshot['pullRequests'] if entry['number'] == number), {})
        if 'omitted' in previous:
            pr['omitted'] = previous['omitted']
        snapshot['pullRequests'] = [entry for entry in snapshot['pullRequests'] if entry['number'] != number] + [pr]
    for omission in omissions:
        target, reason = omission.split('=', 1)
        number, path = target.split(':', 1)
        pr = next(entry for entry in snapshot['pullRequests'] if entry['number'] == int(number))
        pr.setdefault('omitted', {})[path] = reason
    snapshot['pullRequests'].sort(key=lambda pr: pr['number'])
    assets = generate(snapshot)
    provenance_path = ROOT / 'provenance.json'
    provenance = json.loads(provenance_path.read_text())
    managed = provenance.get('lobehubPullRequests', {}).get('files', {})
    if set(managed) - set(assets):
        raise ValueError('Removing a PR would retire published artwork; reconcile it explicitly first')
    for name, data in assets.items():
        target = ROOT / 'assets' / name
        if target.exists():
            if name not in managed:
                raise ValueError(f'Refusing to overwrite existing artwork: {name}')
            if hashlib.sha256(target.read_bytes()).hexdigest() != managed[name]:
                raise ValueError(f'Locally modified PR artwork: {name}')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(assets.items())}
    provenance['lobehubPullRequests'] = {
        'repository': 'https://github.com/lobehub/lobe-icons',
        'sourceSnapshot': 'sources/lobehub-prs.json', 'files': hashes,
    }
    outputs = {ROOT / 'assets' / name: data for name, data in assets.items()}
    outputs[SOURCE] = (json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n').encode()
    outputs[provenance_path] = (json.dumps(provenance, indent=2) + '\n').encode()
    for path, data in outputs.items():
        if check:
            if not path.exists() or path.read_bytes() != data:
                raise ValueError(f'{path.relative_to(ROOT)} is out of date; run npm run sync:lobehub-prs')
        else:
            path.write_bytes(data)
    icons = sum(not entry.get('metadataOnly') for pr in snapshot['pullRequests'] for entry in pr['icons'].values())
    print(f'Reviewed LobeHub PRs: {icons} icons, {len(assets)} SVGs; pinned source hashes verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--add-pr', type=int, action='append', default=[], help='Snapshot/update an explicitly reviewed PR (repeatable)')
    parser.add_argument('--omit', action='append', default=[], metavar='NUMBER:PATH=REASON', help='Record a reviewed artwork omission')
    parser.add_argument('--check', action='store_true', help='Verify the offline replay without writing or fetching')
    args = parser.parse_args()
    if args.check and (args.add_pr or args.omit):
        parser.error('--check cannot add or change reviewed sources')
    sync(args.add_pr, args.omit, args.check)
