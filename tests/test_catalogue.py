import hashlib
import json
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build import ROOT, inline
from sync_lobehub import plan
from sync_lobehub_prs import sync, verified_files, adjust_geometry


class CatalogueTests(unittest.TestCase):
    def test_complete_source_coverage_and_unchanged_originals(self):
        provenance = json.loads((ROOT / 'provenance.json').read_text())
        groups = [provenance['files'], provenance['lobehub']['files'], provenance['lobehubPullRequests']['files']]
        hashes = {name: digest for group in groups for name, digest in group.items()}
        self.assertEqual(len(hashes), sum(map(len, groups)), 'Artwork has exactly one provenance owner')
        self.assertEqual(set(hashes), {p.name for p in (ROOT / 'assets').glob('*.svg')})
        for name, digest in hashes.items():
            self.assertEqual(hashlib.sha256((ROOT / 'assets' / name).read_bytes()).hexdigest(), digest, name)

    def test_reviewed_pr_sources_replay_offline_and_detect_tampering(self):
        sync(check=True)
        pr = copy.deepcopy(json.loads((ROOT / 'sources/lobehub-prs.json').read_text())['pullRequests'][0])
        next(iter(pr['files'].values()))['content'] += '\n'
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            verified_files(pr)

    def test_reviewed_geometry_adjustments_preserve_paths(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 24"><path d="M18 5L29 9"/></svg>'
        adjusted = adjust_geometry(svg, {'viewBox': '18 4.75 11.25 4.5', 'flipY': 24, 'reason': 'Fix source framing'})
        self.assertIn(b'd="M18 5L29 9"', adjusted)
        self.assertIn(b'viewBox="18 4.75 11.25 4.5"', adjusted)
        self.assertIn(b'translate(0 24) scale(1 -1)', adjusted)
        for entry in [{'viewBox': '0 0 -1 1'}, {'viewBox': '0 0 nan 1'}, {'flipY': float('inf')}, {'script': 'bad'}]:
            with self.assertRaises(ValueError):
                adjust_geometry(svg, {**entry, 'reason': 'Invalid adjustment'})

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
                        '<text font-family="Arial">Font-dependent wordmark</text>',
                        '<path onload="alert(1)"/>', '<path fill="url(https://example.com)"/>',
                        '<path style="filter:url(https://example.com)"/>',
                        '<path style="background:url(javascript:alert(1))"/>']:
            with self.assertRaises(ValueError):
                inline(f'<svg xmlns="http://www.w3.org/2000/svg">{content}</svg>')


if __name__ == '__main__':
    unittest.main()
