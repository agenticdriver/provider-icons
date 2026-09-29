import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import vendor

SCRIPT = Path(vendor.__file__)
PACKAGE = json.dumps({'name': '@agenticdriver/provider-icons', 'version': '1.0.0'}).encode()


def tarball(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as archive:
        for name, content in entries:
            member = tarfile.TarInfo(name)
            if content is None:
                member.type, member.linkname = tarfile.SYMTYPE, '../outside'
                archive.addfile(member)
            else:
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
    return data.getvalue()


class VendorTests(unittest.TestCase):
    def invoke(self, directory, data, digest=None):
        archive = directory / 'release.tgz'
        archive.write_bytes(data)
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(archive), '--sha256',
             digest or hashlib.sha256(data).hexdigest(), '--target', str(directory / 'vendor')],
            env={**os.environ, 'PYTHONOPTIMIZE': '1'}, capture_output=True, text=True, timeout=10)

    def test_optimized_cli_rejects_wrong_digest_before_modifying_target(self):
        data = tarball([('package/package.json', PACKAGE)])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'vendor').mkdir()
            old = root / 'vendor/old.svg'
            old.write_text('keep until validated')
            result = self.invoke(root, data, '0' * 64)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Archive digest mismatch', result.stderr)
            self.assertEqual(old.read_text(), 'keep until validated')
            self.assertFalse((root / 'vendor/package.json').exists())

    def test_optimized_cli_rejects_unsafe_and_colliding_archive_paths(self):
        cases = [
            [('package/../escape.svg', b'bad')],
            [('/absolute.svg', b'bad')],
            [('other/file.svg', b'bad')],
            [('package/assets/..\\escape.svg', b'bad')],
            [('package/C:/escape.svg', b'bad')],
            [('package/link', None)],
            [('package/assets/icon.svg', b'a'), ('package/icon.svg', b'b')],
            [('package/one', b'a'), ('package/one/file', b'b')],
            [('package/source.json', b'{}')],
        ]
        for entries in cases:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = self.invoke(root, tarball([('package/package.json', PACKAGE), *entries]))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse((root / 'vendor').exists())

    def test_identity_and_archive_limits(self):
        for metadata in [b'{}', b'[]', b'{"name":"another-package"}']:
            data = tarball([('package/package.json', metadata)])
            with self.assertRaisesRegex(ValueError, 'Unexpected package identity'):
                vendor.package_files(data, hashlib.sha256(data).hexdigest())
        data = tarball([('package/package.json', PACKAGE), ('package/assets/icon.svg', b'<svg/>')])
        for limit, value in [('MAX_ARCHIVE', len(data) - 1), ('MAX_FILE', 1),
                             ('MAX_UNPACKED', len(PACKAGE)), ('MAX_MEMBERS', 1)]:
            with self.subTest(limit=limit), patch.object(vendor, limit, value), self.assertRaises(ValueError):
                vendor.package_files(data, hashlib.sha256(data).hexdigest())

    def test_optimized_cli_vendors_and_removes_only_obsolete_svg_files(self):
        data = tarball([('package/package.json', PACKAGE), ('package/assets/icon.svg', b'<svg/>'),
                        ('package/docs/readme.md', b'hello')])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'vendor').mkdir()
            (root / 'vendor/old.svg').write_text('old')
            (root / 'vendor/keep.txt').write_text('keep')
            result = self.invoke(root, data)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SHA-256 verified', result.stdout)
            self.assertEqual((root / 'vendor/icon.svg').read_bytes(), b'<svg/>')
            self.assertEqual((root / 'vendor/docs/readme.md').read_text(), 'hello')
            self.assertFalse((root / 'vendor/old.svg').exists())
            self.assertEqual((root / 'vendor/keep.txt').read_text(), 'keep')
            self.assertEqual(json.loads((root / 'vendor/source.json').read_text())['sha256'],
                             hashlib.sha256(data).hexdigest())

    def test_existing_symlinks_cannot_redirect_writes(self):
        for name, content in [('icon.svg', b'new'), ('docs/file.md', b'new'), ('source.json', b'{}')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / 'vendor'
                target.mkdir()
                outside = root / 'outside'
                outside.mkdir()
                (outside / 'file.md').write_text('untouched')
                link = target / ('docs' if '/' in name else name)
                link.symlink_to(outside if '/' in name else outside / 'file.md')
                with self.assertRaises(ValueError):
                    vendor.write_package({'package.json': PACKAGE, name: content}, target, {})
                self.assertEqual((outside / 'file.md').read_text(), 'untouched')
                self.assertFalse((target / 'package.json').exists())


if __name__ == '__main__':
    unittest.main()
