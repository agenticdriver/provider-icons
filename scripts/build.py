#!/usr/bin/env python3
"""Generate neutral JSON, portable JS and reviewed inline SVG from one asset set."""
import argparse
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
ET.register_namespace('', 'http://www.w3.org/2000/svg')
TAGS = set('svg path title stop linearGradient defs g feBlend filter feFlood feGaussianBlur polygon radialGradient circle rect feColorMatrix clipPath feOffset feComposite ellipse mask'.split())
ATTRS = set('d fill width height viewBox stop-color fill-rule offset id clip-rule x2 x1 y2 y1 gradientUnits result fill-opacity cx cy x y r in2 transform stroke stop-opacity in stroke-width filter color-interpolation-filters filterUnits flood-opacity stdDeviation gradientTransform points rx stroke-linecap values fx fy vector-effect stroke-linejoin clip-path k2 k3 operator ry maskUnits mask opacity shape-rendering'.split())
ALIASES = {'chatgpt':'openai', 'openai-api':'openai', 'claude-code':'claudecode', 'gemini-cli':'gemini', 'opencodego':'opencode-go', 'kimi-k2':'kimi', 'jetbrains':'jetbrains-ai-assistant', 'xai-responses':'xai'}
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

def outputs():
    icons, svgs = {}, {}
    source = json.loads((ROOT/'sources/lobehub.json').read_text())
    upstream = source['icons']
    extras = {file for entry in upstream.values()
              for artwork, styles in entry['artworks'].items() if artwork != 'icon'
              for file in styles.values()}
    for file in sorted((ROOT/'assets').glob('*.svg')):
        source = file.read_text()
        svgs[file.name] = inline(source)
        if file.stem.endswith('-color') or file.name in extras: continue
        title = ET.fromstring(source).find('{http://www.w3.org/2000/svg}title')
        name = title.text if title is not None else upstream.get(file.stem, {}).get('name', file.stem.replace('-', ' ').title())
        if file.stem == 'openai': name = 'ChatGPT / OpenAI'
        entry = {'name': name, 'monochrome':file.name, 'alternatives':[file.stem]}
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
        'svg.js':"// Generated by scripts/build.py. Do not edit.\nimport {resolveProviderIcon} from './index.js';\nconst svg = "+json.dumps(svgs,separators=(',',':'))+";\nexport function providerIconSvg(provider, options = {}) {\n    const icon = resolveProviderIcon(provider, options);\n    const prefix = options.prefix ?? 'ad-icon';\n    if (!icon || !/^[A-Za-z][A-Za-z0-9_-]{0,100}$/.test(prefix)) return undefined;\n    return svg[icon.file].replaceAll('__AD_ICON__', prefix + '-');\n}\n"
    }

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    for name,content in outputs().items():
        path=ROOT/name
        if args.check:
            assert path.read_text() == content, f'{name} is out of date; run npm run build'
        else: path.write_text(content)
