#!/usr/bin/env python3
"""Snapshot discovery metadata at the already-reviewed artwork revisions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess

from discovery import ROOT, SOURCE, documentation_metadata
from sync_lobehub import download, blob_hash


def github(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def read_source(repository, commit, file):
    data = download(f'https://raw.githubusercontent.com/{repository}/{commit}/{file["path"]}', 1_000_000)
    if blob_hash(data) != file['sha']:
        raise ValueError(f'Changed discovery source: {file["path"]}')
    return {'path': file['path'], 'gitBlob': file['sha'],
            'sha256': hashlib.sha256(data).hexdigest(), 'content': data.decode()}


def sync():
    artwork = json.loads((ROOT / 'sources/lobehub.json').read_text())
    repository, commit = 'lobehub/lobe-icons', artwork['commit']
    toc = github(f'repos/{repository}/contents/src/toc.json?ref={commit}')
    base = read_source(repository, commit, toc)
    if base['sha256'] != artwork['tocSha256']:
        raise ValueError('Discovery catalogue differs from the reviewed artwork catalogue')
    prs = json.loads((ROOT / 'sources/lobehub-prs.json').read_text())['pullRequests']

    def read_pr(pr):
        files, missing = {}, []
        for id, entry in pr['icons'].items():
            if entry.get('metadataOnly'):
                continue
            directory = f'src/{entry["componentName"]}'
            listing = github(f'repos/{pr["repository"]}/contents/{directory}?ref={pr["commit"]}')
            candidates = [file for file in listing if file['name'] in {'index.md', 'index.mdx'}]
            if not candidates:
                missing.append(id)
                continue
            if len(candidates) != 1:
                raise ValueError(f'Ambiguous documentation source: {directory}')
            file = read_source(pr['repository'], pr['commit'], candidates[0])
            documentation_metadata(file['content'], pr['url'])
            files[id] = file
        if not files and not missing:
            return None
        return str(pr['number']), {'repository': pr['repository'], 'commit': pr['commit'],
                                  'files': files, 'missingDocumentation': missing}

    with ThreadPoolExecutor(8) as pool:
        entries = dict(entry for entry in pool.map(read_pr, prs) if entry)
    snapshot = {'version': 1, 'base': {'repository': repository, 'commit': commit, **base}, 'pullRequests': entries}
    SOURCE.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n')
    print(f'Snapshotted discovery metadata: {len(json.loads(base["content"]))} mainline and {sum(len(pr["files"]) for pr in entries.values())} PR entries; Git blobs verified')


if __name__ == '__main__':
    sync()
