"""Source-backed category and alternate-name metadata for the icon catalogue."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'sources/lobehub-discovery.json'
CATEGORIES = {'application', 'model', 'provider'}


def verified_content(entry):
    data = entry['content'].encode()
    if (hashlib.sha256(data).hexdigest() != entry['sha256'] or
            hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() != entry['gitBlob']):
        raise ValueError(f'Discovery source digest mismatch: {entry["path"]}')
    return entry['content']


def metadata(title, category, source_url, *terms):
    if category not in CATEGORIES or not isinstance(title, str) or not title.strip():
        raise ValueError('Invalid discovery metadata')
    return {'fullName': title, 'category': category,
            'searchTerms': list(dict.fromkeys([title, *terms])), 'upstreamUrl': source_url}


def documentation_metadata(content, source_url):
    match = re.match(r'\A---\r?\n(.*?)\r?\n---', content, re.S)
    if not match:
        raise ValueError('Missing documentation frontmatter')
    header = match[1]
    title = re.search(r'^title:\s*(.+)$', header, re.M)
    category = re.search(r'^(?:category|group):[ \t]*(Application|Model|Provider)[ \t]*$', header, re.M)
    if not category:
        category = re.search(r'^group:[ \t]*\n[ \t]+title:[ \t]*(Application|Model|Provider)[ \t]*$', header, re.M)
    if not title or not category:
        raise ValueError('Documentation needs a literal title and category')
    return metadata(title[1].strip().strip('"\''), category[1].lower(), source_url)


def discovery_metadata():
    source = json.loads(SOURCE.read_text())
    artwork = json.loads((ROOT / 'sources/lobehub.json').read_text())
    if source['base']['commit'] != artwork['commit'] or source['base']['sha256'] != artwork['tocSha256']:
        raise ValueError('Discovery metadata must match the artwork revision; run npm run sync:discovery')
    entries = json.loads(verified_content(source['base']))
    result = {}
    for entry in entries:
        key = entry['id'].lower()
        if key not in artwork['icons'] or key in result or not re.fullmatch(r'[a-z0-9-]+', entry['docsUrl']):
            raise ValueError(f'Unexpected discovery entry: {key}')
        result[key] = metadata(entry['fullTitle'], entry['group'],
                               f'https://icons.lobehub.com/components/{entry["docsUrl"]}', entry['title'])
    prs = json.loads((ROOT / 'sources/lobehub-prs.json').read_text())['pullRequests']
    expected = {str(pr['number']): pr for pr in prs if any(not entry.get('metadataOnly') for entry in pr['icons'].values())}
    if set(expected) != set(source['pullRequests']):
        raise ValueError('PR discovery metadata is out of date; run npm run sync:discovery')
    for number, pr in source['pullRequests'].items():
        artwork_pr = expected[number]
        if pr['commit'] != artwork_pr['commit'] or pr['repository'] != artwork_pr['repository']:
            raise ValueError(f'PR #{number} discovery revision is out of date; run npm run sync:discovery')
        ids = {id for id, entry in artwork_pr['icons'].items() if not entry.get('metadataOnly')}
        if set(pr['files']) | set(pr['missingDocumentation']) != ids or set(pr['files']) & set(pr['missingDocumentation']):
            raise ValueError(f'Incomplete PR #{number} discovery metadata')
        for id, entry in pr['files'].items():
            folder = artwork_pr['icons'][id]['componentName']
            if entry['path'] not in {f'src/{folder}/index.md', f'src/{folder}/index.mdx'}:
                raise ValueError(f'Unexpected documentation path: {entry["path"]}')
            result[id] = documentation_metadata(verified_content(entry), f'https://github.com/lobehub/lobe-icons/pull/{number}')
    # A reviewed title correction must not leave the old incorrect name searchable.
    for pr in prs:
        for id, entry in pr['icons'].items():
            if entry.get('metadataOnly') and id in result:
                result[id]['fullName'] = entry['name']
                result[id]['searchTerms'] = [entry['name']]
    return result
