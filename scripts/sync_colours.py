#!/usr/bin/env python3
"""Snapshot colour definitions at the already-reviewed artwork source revision."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from sync_lobehub import ROOT, download, blob_hash


def sync():
    source = json.loads((ROOT / 'sources/lobehub.json').read_text())
    commit = source['commit']
    tree = json.loads(download(f'https://api.github.com/repos/lobehub/lobe-icons/git/trees/{commit}?recursive=1'))
    if tree.get('truncated'):
        raise ValueError('Incomplete source tree')
    files = [item for item in tree['tree'] if item['type'] == 'blob'
             and len(Path(item['path']).parts) == 3 and item['path'].startswith('src/')
             and item['path'].endswith('/style.ts')
             and Path(item['path']).parent.name.lower() in source['icons']]

    def read(item):
        data = download(f'https://raw.githubusercontent.com/lobehub/lobe-icons/{commit}/{item["path"]}', 64_000)
        if blob_hash(data) != item['sha']:
            raise ValueError(f'Changed source: {item["path"]}')
        return Path(item['path']).parent.name.lower(), {
            'path': item['path'], 'gitBlob': item['sha'],
            'sha256': hashlib.sha256(data).hexdigest(), 'content': data.decode(),
        }

    with ThreadPoolExecutor(8) as pool:
        entries = dict(sorted(pool.map(read, files)))
    snapshot = {'repository': source['repository'], 'commit': commit, 'files': entries}
    (ROOT / 'sources/lobehub-colours.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    print(f'Snapshotted {len(entries)} colour definitions at {commit}; every Git blob verified')


if __name__ == '__main__':
    sync()
