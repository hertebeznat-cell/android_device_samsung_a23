#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline test of releasetools.py with a stand-in for AOSP's common module."""
import importlib.util
import pathlib
import sys
import types
import unittest

DEVICE = pathlib.Path(__file__).resolve().parent.parent


class FakeZip:
    def __init__(self, entries):
        self.entries = entries
        self.written = {}

    def namelist(self):
        return list(self.entries)

    def read(self, name):
        return self.entries[name]


class FakeScript:
    def __init__(self):
        self.raw = []

    def Print(self, message):
        pass

    def WriteRawImage(self, mount, name):
        self.raw.append((mount, name))


def load(common):
    sys.modules['common'] = common
    spec = importlib.util.spec_from_file_location('releasetools', DEVICE / 'releasetools.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleasetoolsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        common = types.ModuleType('common')
        common.GetUserImage = lambda partition, tmp, zip_, **kw: self.calls.append((partition, kw)) or f'image:{partition}'
        common.BlockDifference = lambda partition, image, src=None: (partition, image, src)
        common.ZipWriteStr = lambda output, name, data: output.written.__setitem__(name, data)
        self.module = load(common)

    def info(self, entries):
        return types.SimpleNamespace(input_zip=FakeZip(entries), output_zip=FakeZip({}),
                                     input_tmp='/tmp/target', info_dict={}, script=FakeScript())

    def test_full_ota_writes_stock_vendor_and_odm(self):
        diffs = self.module.FullOTA_GetBlockDifferences(self.info({}))
        self.assertEqual(diffs, [('vendor', 'image:vendor', None), ('odm', 'image:odm', None)])
        self.assertTrue(all(kw['reset_file_map'] for _, kw in self.calls))

    def test_dtbo_from_prebuilt_images(self):
        info = self.info({'PREBUILT_IMAGES/dtbo.img': b'dtbo'})
        self.module.FullOTA_InstallEnd(info)
        self.assertEqual(info.output_zip.written, {'dtbo.img': b'dtbo'})
        self.assertEqual(info.script.raw, [('/dtbo', 'dtbo.img')])

    def test_missing_dtbo_fails_the_package(self):
        with self.assertRaises(ValueError):
            self.module.FullOTA_InstallEnd(self.info({}))

    def test_no_incremental_override(self):
        self.assertIsNone(self.module.IncrementalOTA_GetBlockDifferences(self.info({})))


if __name__ == '__main__':
    unittest.main()
