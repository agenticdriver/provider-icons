#!/usr/bin/env python3
"""Replay reviewed, source-pinned provider artwork without fetching or executing it."""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

from build import ROOT, inline, verified_content

SOURCE = ROOT / 'sources/inspiration.json'
NS = '{http://www.w3.org/2000/svg}'


def monochrome(source, mode):
    root = ET.fromstring(source)
    # Consumers own labels; the original labelled SVG is retained in the snapshot.
    root.attrib.pop('aria-labelledby', None)
    if mode == 'ink':
        root.set('fill', root.get('fill', 'currentColor'))
        def recolour(node):
            if node.tag in {NS + 'mask', NS + 'clipPath', NS + 'defs'}:
                return
            for attribute in ('fill', 'stroke'):
                if node.get(attribute, '').lower() in {'black', 'white', '#000', '#000000', '#fff', '#ffffff'}:
                    node.set(attribute, 'currentColor')
            for child in node:
                recolour(child)
        recolour(root)
    elif mode == 'luminance':
        # Invert source luminance into ink opacity: white cutouts remain empty,
        # dark detail remains visible, and gradients retain tonal separation.
        x, y, width, height = root.attrib['viewBox'].split()
        output = ET.Element(NS + 'svg', {'viewBox': root.attrib['viewBox']})
        defs = ET.SubElement(output, NS + 'defs')
        filter_node = ET.SubElement(defs, NS + 'filter', {'id': 'inspiration-ink'})
        ET.SubElement(filter_node, NS + 'feColorMatrix', {'values':
            '-0.2126 -0.7152 -0.0722 0 1 -0.2126 -0.7152 -0.0722 0 1 -0.2126 -0.7152 -0.0722 0 1 0 0 0 1 0'})
        mask = ET.SubElement(defs, NS + 'mask', {'id': 'inspiration-mask',
            'maskUnits': 'userSpaceOnUse', 'x': x, 'y': y, 'width': width, 'height': height,
            'style': 'mask-type:luminance'})
        group = ET.SubElement(mask, NS + 'g', {'filter': 'url(#inspiration-ink)'})
        # Keep source coordinate space and inherited presentation attributes.
        root.set('x', x)
        root.set('y', y)
        root.set('width', width)
        root.set('height', height)
        group.append(root)
        ET.SubElement(output, NS + 'rect', {'x': x, 'y': y, 'width': width, 'height': height,
            'fill': 'currentColor', 'mask': 'url(#inspiration-mask)'})
        root = output
    else:
        raise ValueError(f'Unknown monochrome conversion: {mode}')
    return (ET.tostring(root, encoding='unicode') + '\n').encode()


def generate(snapshot):
    assets = {}
    for id, entry in snapshot['icons'].items():
        source = verified_content(entry['source'])
        assets[f'{id}.svg'] = monochrome(source, entry['monochrome'])
        if entry['monochrome'] == 'luminance':
            assets[f'{id}-color.svg'] = source.encode()
    for data in assets.values():
        inline(data.decode())
    return assets


def sync(check=False):
    snapshot = json.loads(SOURCE.read_text())
    assets = generate(snapshot)
    provenance_path = ROOT / 'provenance.json'
    provenance = json.loads(provenance_path.read_text())
    managed = provenance.get('inspiration', {}).get('files', {})
    if set(managed) - assets.keys():
        raise ValueError('Removing published artwork requires explicit reconciliation')
    for name in assets:
        target = ROOT / 'assets' / name
        if target.exists() and (name not in managed or hashlib.sha256(target.read_bytes()).hexdigest() != managed[name]):
            raise ValueError(f'Refusing to overwrite unowned or modified artwork: {name}')
    provenance['inspiration'] = {'sourceSnapshot': 'sources/inspiration.json',
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(assets.items())}}
    outputs = {ROOT / 'assets' / name: data for name, data in assets.items()}
    outputs[provenance_path] = (json.dumps(provenance, indent=2) + '\n').encode()
    for path, data in outputs.items():
        if check:
            if not path.exists() or path.read_bytes() != data:
                raise ValueError(f'{path.relative_to(ROOT)} is out of date; run npm run sync:inspiration')
        else:
            path.write_bytes(data)
    print(f'Reviewed inspiration sources: {len(snapshot["icons"])} icons, {len(assets)} SVGs; source hashes verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(parser.parse_args().check)
