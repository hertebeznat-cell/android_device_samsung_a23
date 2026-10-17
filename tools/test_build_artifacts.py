"""Exercise stale/wrong/corrupt artifact rejection without a ROM build."""
import os
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from check_build_artifacts import find_ota, main


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='a23-artifact-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def zip(self, name, metadata, timestamp=200):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('META-INF/com/android/metadata', metadata)
        os.utime(path, (timestamp, timestamp))
        return path

    def test_rejects_old_ota_even_if_a_build_returned_success(self):
        self.zip('old.zip', 'pre-device=a23\n', timestamp=100)
        with self.assertRaisesRegex(ValueError, 'No fresh A23 OTA'):
            find_ota(self.root, 150)

    def test_rejects_other_device_and_non_ota_archives(self):
        self.zip('other.zip', 'pre-device=a23xq\n')
        (self.root / 'broken.zip').write_bytes(b'not a zip')
        with zipfile.ZipFile(self.root / 'arbitrary.zip', 'w') as archive:
            archive.writestr('hello.txt', 'not an OTA')
        with self.assertRaises(ValueError):
            find_ota(self.root, 150)

    def test_selects_newest_matching_ota_and_allows_assert_aliases(self):
        self.zip('first.zip', 'pre-device=a23\n', timestamp=200)
        newest = self.zip('newest.zip', 'pre-device=a23ns|a23\nota-type=BLOCK\n', timestamp=201)
        self.zip('wrong.zip', 'pre-device=a23xq\n', timestamp=202)
        self.assertEqual(find_ota(self.root, 150), newest)

    def test_cli_writes_correct_checksums_without_python311_file_digest(self):
        ota = self.zip('fresh A23.zip', 'pre-device=a23\n')
        images = []
        for name in ('boot.img', 'dtbo.img', 'vbmeta.img', 'recovery.img'):
            path = self.root / name
            path.write_bytes((name + '\n').encode())
            images.append(path)
        checksums = self.root / 'SHA256SUMS result'
        arguments = ['check_build_artifacts.py', str(self.root), '--since', '150',
                     '--checksums', str(checksums)]
        output = io.StringIO()
        # Ubuntu hosts with Python 3.10 do not have this Python 3.11 helper.
        with patch.object(hashlib, 'file_digest', None, create=True), \
                patch.object(sys, 'argv', arguments), redirect_stdout(output):
            main()
        expected = [f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.resolve()}'
                    for path in [ota, *images]]
        self.assertEqual(checksums.read_text().splitlines(), expected)
        self.assertIn(f'ROM_FILE={ota.resolve()}', output.getvalue())

    def test_cli_rejects_missing_required_image_without_success_checksum_file(self):
        self.zip('fresh.zip', 'pre-device=a23\n')
        checksums = self.root / 'SHA256SUMS'
        arguments = ['check_build_artifacts.py', str(self.root), '--since', '150',
                     '--checksums', str(checksums)]
        error_output = io.StringIO()
        with patch.object(sys, 'argv', arguments), redirect_stderr(error_output):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 1)
        self.assertIn('Required build image is missing or empty', error_output.getvalue())
        self.assertFalse(checksums.exists())


if __name__ == '__main__':
    unittest.main()
