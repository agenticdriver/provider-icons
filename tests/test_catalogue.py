import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build import ROOT, inline
from sync_lobehub import plan


class CatalogueTests(unittest.TestCase):
    def test_complete_source_coverage_and_unchanged_originals(self):
        provenance = json.loads((ROOT / 'provenance.json').read_text())
        hashes = {**provenance['files'], **provenance['lobehub']['files']}
        self.assertFalse(set(provenance['files']) & set(provenance['lobehub']['files']))
        self.assertEqual(set(hashes), {p.name for p in (ROOT / 'assets').glob('*.svg')})
        for name, digest in hashes.items():
            self.assertEqual(hashlib.sha256((ROOT / 'assets' / name).read_bytes()).hexdigest(), digest, name)

    def test_import_plan_covers_variants_without_creating_extra_icons(self):
        result = plan([{'id': 'Example', 'title': 'Example AI'}],
                      {'example.svg', 'example-color.svg', 'example-text.svg', 'example-brand.svg'})
        self.assertEqual(list(result), ['example'])
        self.assertEqual(result['example']['artworks']['text'], {'monochrome': 'example-text.svg'})

    def test_incomplete_or_unknown_upstream_artwork_fails(self):
        toc = [{'id': 'Example', 'title': 'Example'}]
        for files in [{'example-color.svg'}, {'example.svg', 'example-unexpected.svg'},
                      {'example.svg', 'example-brand-color.svg'}]:
            with self.assertRaises(ValueError):
                plan(toc, files)
        with self.assertRaises(ValueError):
            plan(toc + toc, {'example.svg'})

    def test_safe_rendering_styles_survive_but_active_content_is_rejected(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" style="flex:none;line-height:1;filter:grayscale(100%)"><path style="mix-blend-mode:screen" d="M0 0"/></svg>'
        output = inline(svg)
        self.assertIn('filter:grayscale(100%)', output)
        self.assertIn('mix-blend-mode:screen', output)
        self.assertNotIn('flex', output)
        for content in ['<script/>', '<use href="https://example.com/icon.svg"/>',
                        '<path onload="alert(1)"/>', '<path fill="url(https://example.com)"/>',
                        '<path style="filter:url(https://example.com)"/>',
                        '<path style="background:url(javascript:alert(1))"/>']:
            with self.assertRaises(ValueError):
                inline(f'<svg xmlns="http://www.w3.org/2000/svg">{content}</svg>')


if __name__ == '__main__':
    unittest.main()
