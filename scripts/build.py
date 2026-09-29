#!/usr/bin/env python3
"""Generate neutral JSON, portable JS and reviewed inline SVG from one asset set."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
ET.register_namespace('', 'http://www.w3.org/2000/svg')
TAGS = set('svg path title stop linearGradient defs g feBlend filter feFlood feGaussianBlur polygon radialGradient circle rect feColorMatrix clipPath feOffset feComposite ellipse mask line'.split())
ATTRS = set('d fill width height viewBox stop-color fill-rule offset id clip-rule x2 x1 y2 y1 gradientUnits result fill-opacity cx cy x y r in2 transform stroke stop-opacity in stroke-width stroke-opacity filter color-interpolation-filters filterUnits flood-opacity stdDeviation gradientTransform points rx stroke-linecap values fx fy vector-effect stroke-linejoin clip-path k2 k3 operator ry maskUnits mask opacity shape-rendering'.split())
ALIASES = {'chatgpt':'openai', 'openai-api':'openai', 'claude-code':'claudecode', 'gemini-cli':'gemini', 'opencodego':'opencode-go', 'kimi-k2':'kimi', 'jetbrains':'jetbrains-ai-assistant', 'xai-responses':'xai', '5dive':'fivedive'}
GROUPS = [('openai', 'codex'), ('anthropic', 'claude', 'claudecode'), ('copilot', 'githubcopilot'), ('xai', 'grok'), ('opencode-go', 'opencode')]
# Exact rendering declarations only; remove React's layout styles without losing
# masks, intentional monochrome filters or colour blending in the original art.
STYLES = {'mask-type': {'alpha', 'luminance'},
          'mix-blend-mode': {'overlay', 'screen'}, 'filter': {'grayscale(100%)'},
          'stroke-width': {'1'}}

def rendering_style(source):
    result = []
    for declaration in source.split(';'):
        if not declaration.strip(): continue
        key, value = (part.strip() for part in declaration.split(':', 1))
        if (key, value) in {('flex', 'none'), ('line-height', '1')}: continue
        if value not in STYLES.get(key, set()):
            raise ValueError(f'Unsupported SVG style {key}: {value}')
        result.append(f'{key}:{value}')
    return ';'.join(result)

def inline(source):
    source = re.sub(r'<!--.*?-->', '', source, flags=re.S)
    source = re.sub(r'<\?xml [^?]*\?>', '', source)
    source = re.sub(r'<!DOCTYPE svg PUBLIC [^<>\[\]]*>', '', source)
    if '<!' in source or '<?' in source: raise ValueError('SVG declarations are not supported')
    root = ET.fromstring(source)
    for node in root.iter():
        tag = node.tag.removeprefix('{http://www.w3.org/2000/svg}')
        if tag not in TAGS: raise ValueError(f'Unsupported SVG tag {tag}')
        for attr, value in list(node.attrib.items()):
            if attr == 'style':
                style = rendering_style(value)
                if style: node.set(attr, style)
                else: del node.attrib[attr]
                continue
            if attr in ('role', 'aria-label', 'version', 'class'):
                del node.attrib[attr]
                continue
            if attr not in ATTRS or re.search(r'(?:https?:|data:|javascript:|[<>])', value, re.I):
                raise ValueError(f'Unsupported SVG attribute {attr}')
            if 'url(' in value and not re.fullmatch(r'url\(#[A-Za-z0-9_.-]+\)', value):
                raise ValueError('External SVG reference')
            if attr == 'id':
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', value): raise ValueError('Invalid SVG id')
                node.set(attr, '__AD_ICON__' + value)
            elif 'url(#' in value: node.set(attr, value.replace('url(#', 'url(#__AD_ICON__'))
        for child in list(node):
            if child.tag.endswith('}title'): node.remove(child)
    root.set('aria-hidden', 'true')
    root.set('focusable', 'false')
    return ET.tostring(root, encoding='unicode')

COMPONENT_NAMES = {
    'xai': 'XAI', 'microsoft': 'Microsoft', 'kilo': 'Kilo',
    'opencode-go': 'OpenCodeGo', 'opencode': 'OpenCode', 'happyhorse': 'HappyHorse',
    'xuanyuan': 'Xuanyuan', 'jetbrains-ai-assistant': 'JetBrainsAIAssistant',
    'zeroone': 'ZeroOne', 'elevenx': 'ElevenX', 'ai302': 'Ai302',
    'githubcopilot': 'GitHubCopilot',
}

def verified_content(entry):
    data = entry['content'].encode()
    if hashlib.sha256(data).hexdigest() != entry['sha256'] or hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest() != entry['gitBlob']:
        raise ValueError('Source digest mismatch')
    return entry['content']

def colour_theme(content):
    values = dict(re.findall(r"export const (COLOR_[A-Z0-9_]+) = ['\"](#[0-9a-fA-F]{3,8})['\"];", content))
    def hex(value):
        value = value[1:]
        if len(value) in (3, 4): value = ''.join(c*2 for c in value)
        if len(value) not in (6, 8): raise ValueError('Invalid source colour')
        return '#'+value.upper()
    primary = hex(values['COLOR_PRIMARY'])
    palette = list(dict.fromkeys([primary, *(hex(value) for value in values.values())]))
    return {'primaryColour': primary, 'colourTheme': palette}

def colour_themes():
    source = json.loads((ROOT/'sources/lobehub-colours.json').read_text())
    if source['commit'] != json.loads((ROOT/'sources/lobehub.json').read_text())['commit']:
        raise ValueError('Colour definitions must use the reviewed artwork revision; run sync:colours')
    themes = {}
    for id, entry in source['files'].items():
        themes[id] = colour_theme(verified_content(entry))
    return themes

def pull_request_metadata(upstream, themes):
    snapshot = json.loads((ROOT/'sources/lobehub-prs.json').read_text())
    names = {}
    for pr in snapshot['pullRequests']:
        for source in pr['files'].values(): verified_content(source)
        for id, entry in pr['icons'].items():
            if id in names: raise ValueError(f'Duplicate PR icon: {id}')
            if not entry.get('metadataOnly') and id in upstream:
                raise ValueError(f'{id} now exists upstream; reconcile its reviewed PR source')
            if entry.get('metadataOnly') and id not in upstream:
                raise ValueError(f'Missing original icon for PR metadata: {id}')
            upstream[id] = {**upstream.get(id, {}), **entry}
            names[id] = entry['name']
            themes[id] = colour_theme(pr['files'][f'src/{entry["componentName"]}/style.ts']['content'])
    return names

def react_outputs(icons, svgs, upstream):
    names, files = {}, {}
    exports = ["'use client';", '// Generated by scripts/build.py. Do not edit.',
               "export {ProviderIcon} from './react-provider.js';"]
    types = ["import type {ForwardRefExoticComponent, RefAttributes, SVGProps} from 'react';",
             "import type {IconStyle, ProviderIconTheme} from './index.js';", "import type {IconLayout} from './svg.js';",
             "export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'width' | 'height' | 'children' | 'dangerouslySetInnerHTML'> {",
             "  /** Height in pixels; width follows the artwork. Defaults to 24. */ size?: number;",
             "  mode?: IconStyle;", "  /** Normally generated automatically. */ prefix?: string;", "}",
             "export type IconComponent = ForwardRefExoticComponent<IconProps & RefAttributes<SVGSVGElement>>;",
             "export interface ProviderIconProps extends IconProps {provider: string; artwork?: IconLayout; variant?: string}",
             "export const ProviderIcon: ForwardRefExoticComponent<ProviderIconProps & RefAttributes<SVGSVGElement>>;"]
    for id, entry in icons.items():
        name = COMPONENT_NAMES.get(id) or upstream.get(id, {}).get('componentName')
        if not name:
            title = upstream.get(id, {}).get('name', entry['name'])
            name = ''.join(part[:1].upper()+part[1:] for part in re.findall(r'[A-Za-z0-9]+', title))
        if not re.fullmatch(r'[A-Z][A-Za-z0-9]*', name or ''):
            raise ValueError(f'Add an explicit React component name for {id}')
        if name in names.values() or name in {'ProviderIcon', 'IconComponent', 'IconProps', 'ProviderIconProps'}:
            raise ValueError(f'Duplicate/reserved React component name {name}')
        names[id] = name
        artwork = {'icon': {k: svgs[v] for k,v in entry.items() if k in ('monochrome','color')}}
        for key, styles in entry.get('artworks', {}).items():
            artwork[key] = {style: svgs[file] for style, file in styles.items()}
        files[f'react/{id}.js'] = ("'use client';\n// Generated by scripts/build.py. Do not edit.\n"
            + "import {createNamedIcon} from '../react-runtime.js';\n"
            + f'export const {name} = /* @__PURE__ */ createNamedIcon({json.dumps(name)}, '
            + json.dumps(artwork, separators=(',', ':')) + ', '
            + json.dumps({'primaryColour': entry.get('primaryColour'), 'colourTheme': entry['colourTheme']}, separators=(',', ':')) + ');\n')
        exports.append(f"export {{{name}}} from './react/{id}.js';")
        members = ['Color', 'Avatar']
        if 'text' in artwork: members += ['Text', 'TextColor', 'Combine']
        if 'brand' in artwork: members += ['Brand', 'BrandColor']
        if 'text-cn' in artwork: members += ['TextCn', 'TextCnColor']
        types.append(f'export const {name}: IconComponent & ProviderIconTheme & {{' + ''.join(f'{key}: IconComponent; ' for key in members) + '};')
    files['react.js'] = '\n'.join(exports)+'\n'
    files['react.d.ts'] = '// Generated by scripts/build.py. Do not edit.\n'+'\n'.join(types)+'\n'
    files['react-names.js'] = '// Generated by scripts/build.py. Do not edit.\nexport const providerIconComponentNames = Object.freeze('+json.dumps(names, separators=(',',':'))+');\n'
    return files

def outputs():
    icons, svgs = {}, {}
    themes = colour_themes()
    source = json.loads((ROOT/'sources/lobehub.json').read_text())
    upstream = source['icons']
    reviewed_names = pull_request_metadata(upstream, themes)
    extras = {file for entry in upstream.values()
              for artwork, styles in entry['artworks'].items() if artwork != 'icon'
              for file in styles.values()}
    for file in sorted((ROOT/'assets').glob('*.svg')):
        source = file.read_text()
        svgs[file.name] = inline(source)
        if file.stem.endswith('-color') or file.name in extras: continue
        title = ET.fromstring(source).find('{http://www.w3.org/2000/svg}title')
        name = title.text if title is not None else upstream.get(file.stem, {}).get('name', file.stem.replace('-', ' ').title())
        name = reviewed_names.get(file.stem, name)
        if file.stem == 'openai': name = 'ChatGPT / OpenAI'
        entry = {'name': name, 'monochrome':file.name, 'alternatives':[file.stem],
                 **themes.get(file.stem, {'colourTheme': []})}
        if (ROOT/'assets'/f'{file.stem}-color.svg').exists(): entry['color'] = f'{file.stem}-color.svg'
        artworks = {key: value for key, value in upstream.get(file.stem, {}).get('artworks', {}).items() if key != 'icon'}
        if artworks: entry['artworks'] = artworks
        icons[file.stem] = entry
    for group in GROUPS:
        for key in group: icons[key]['alternatives'] = list(group)
    assert all(value in icons for value in ALIASES.values())
    assert not set(ALIASES) & set(icons), 'Aliases must not shadow actual icons'
    referenced = {file for entry in icons.values()
                  for artwork in [entry, *entry.get('artworks', {}).values()]
                  for style, file in artwork.items() if style in ('monochrome', 'color')}
    assert referenced == set(svgs), 'Every SVG must have a catalogue entry'
    manifest = {'version':1, 'packageVersion':json.loads((ROOT/'package.json').read_text())['version'], 'icons':icons, 'aliases':ALIASES}
    return {
        'manifest.json':json.dumps(manifest, indent=2)+'\n',
        'manifest.js':'// Generated by scripts/build.py. Do not edit.\nexport const catalog = '+json.dumps(manifest, separators=(',',':'))+';\n',
        'svg-data.js':'// Generated by scripts/build.py. Do not edit.\nexport const svg = '+json.dumps(svgs,separators=(',',':'))+';\n',
        **react_outputs(icons, svgs, upstream),
    }

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    for name,content in outputs().items():
        path=ROOT/name
        if args.check:
            assert path.read_text() == content, f'{name} is out of date; run npm run build'
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
