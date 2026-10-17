"""Regression checks with tiny policy/output fixtures; no compiler or download."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from check_selinux_ownership import (CACHES, DEVICE, EXPORTS, PATCH_NAME, audit,
                                     audit_outputs, reverse_patch)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary_root = DEVICE.parents[2] / '.selinux-test-tmp'
        temporary_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='case-', dir=temporary_root)
        self.addCleanup(lambda: temporary_root.rmdir() if temporary_root.exists() and
                        not any(temporary_root.iterdir()) else None)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.device = self.root / 'device/samsung/a23'
        self.vendor = self.root / 'vendor/samsung/a235f'
        self.stock = self.vendor / 'proprietary/vendor/etc/selinux'
        self.stock.mkdir(parents=True)
        self.device.mkdir(parents=True)
        (self.device / 'BoardConfig.mk').write_text(
            '$(call soong_config_set_bool,a23,use_stock_vendor_policy,true)\n')
        (self.device / 'device.mk').write_text('PRODUCT_PACKAGES += selinux_policy\n')
        (self.vendor / 'a235f-vendor.mk').write_text('# No competing policy copies\n')
        groups = []
        for name, filename in EXPORTS.items():
            groups.append('filegroup {\n'
                          f'    name: "{name}",\n'
                          f'    srcs: ["proprietary/vendor/etc/selinux/{filename}"],\n'
                          '    visibility: ["//system/sepolicy:__subpackages__"],\n}\n')
            (self.stock / filename).write_text(
                '30.0\n' if filename == 'plat_sepolicy_vers.txt' else
                '<policy><signer signature="00"><seinfo value="vendor"/></signer></policy>\n'
                if filename.endswith('.xml') else
                'user=_app seinfo=vendor domain=vendor_fixture type=vendor_data_file\n'
                if filename == 'vendor_seapp_contexts' else
                '/vendor/bin/fixture u:object_r:vendor_fixture_exec:s0\n'
                if filename.endswith('_contexts') else
                '(type vendor_fixture)\n')
        (self.vendor / 'Android.bp').write_text('\n'.join(groups))
        patch_dir = self.device / 'patches/sepolicy'
        patch_dir.mkdir(parents=True)
        for name in (PATCH_NAME, 'sources.json'):
            shutil.copyfile(DEVICE / 'patches/sepolicy' / name, patch_dir / name)
        lock = json.loads((DEVICE / 'source-lock.json').read_text())
        lock['sepolicy_owner_patch_sha256'] = hashlib.sha256((patch_dir / PATCH_NAME).read_bytes()).hexdigest()
        (self.device / 'source-lock.json').write_text(json.dumps(lock))
        old_dir = self.vendor / 'proprietary/odm/etc/selinux'
        old_dir.mkdir(parents=True)
        (old_dir / 'precompiled_sepolicy').write_bytes(b'old Samsung policy')

    def staged_output(self):
        output = self.root / 'out/target/product/a23'
        vendor_out = output / 'vendor/etc/selinux'
        vendor_out.mkdir(parents=True)
        for filename in EXPORTS.values():
            shutil.copyfile(self.stock / filename, vendor_out / filename)
        odm_out = output / 'odm/etc/selinux'
        odm_out.mkdir(parents=True)
        (odm_out / 'precompiled_sepolicy').write_bytes(b'new compiled platform plus stock vendor')
        for partition, prefix in (('system', 'plat'), ('system_ext', 'system_ext'), ('product', 'product')):
            directory = output / partition / 'etc/selinux'
            (directory / 'mapping').mkdir(parents=True)
            policy = f'new {prefix} platform\n'.encode()
            mapping = f'{prefix} map 30\n'.encode()
            (directory / f'{prefix}_sepolicy.cil').write_bytes(policy)
            (directory / 'mapping/30.0.cil').write_bytes(mapping)
            digest = hashlib.sha256(policy + mapping).hexdigest() + '\n'
            (directory / f'{prefix}_sepolicy_and_mapping.sha256').write_text(digest)
            (odm_out / f'precompiled_sepolicy.{prefix}_sepolicy_and_mapping.sha256').write_text(digest)
        return output

    def test_single_owner_configuration_and_fresh_outputs_pass(self):
        self.assertEqual(audit(self.root), [])
        self.assertEqual(audit_outputs(self.root, self.staged_output()), [])

    def test_competing_copy_reintroduced_is_rejected(self):
        path = self.vendor / 'a235f-vendor.mk'
        for filename in EXPORTS.values():
            with self.subTest(filename=filename):
                path.write_text(f'    vendor/fixture:{"$(TARGET_COPY_OUT_VENDOR)"}/etc/selinux/{filename} \\\n')
                self.assertTrue(any('Competing stock SELinux copy' in error for error in audit(self.root)))

    def test_obsolete_odm_binary_and_hash_copies_are_rejected(self):
        path = self.vendor / 'a235f-vendor.mk'
        for filename in CACHES:
            with self.subTest(filename=filename):
                path.write_text(f'    vendor/fixture:{"$(TARGET_COPY_OUT_ODM)"}/etc/selinux/{filename}\n')
                self.assertTrue(any('Competing stock SELinux copy' in error for error in audit(self.root)))

    def test_disabled_or_competing_selector_is_rejected(self):
        path = self.device / 'BoardConfig.mk'
        path.write_text('$(call soong_config_set_bool,a23,use_stock_vendor_policy,false)\n')
        self.assertTrue(any('selector' in error for error in audit(self.root)))
        path.write_text('$(call soong_config_set_bool,a23,use_stock_vendor_policy,true)\n'
                        '$(call soong_config_set_bool,a23,use_stock_vendor_policy,false)\n')
        self.assertTrue(any('selector' in error for error in audit(self.root)))

    def test_untyped_string_selector_cannot_enable_boolean_policy_selection(self):
        path = self.device / 'BoardConfig.mk'
        untyped = '$(call soong_config_set,a23,use_stock_vendor_policy,true)\n'
        for content in (untyped,
                        '$(call soong_config_set_bool,a23,use_stock_vendor_policy,true)\n' + untyped):
            with self.subTest(selector=content):
                path.write_text(content)
                self.assertTrue(any('typed-boolean' in error for error in audit(self.root)))

    def test_export_to_different_source_or_invisible_to_platform_is_rejected(self):
        path = self.vendor / 'Android.bp'
        original = path.read_text()
        path.write_text(original.replace('proprietary/vendor/etc/selinux/vendor_sepolicy.cil', 'proprietary/wrong.cil'))
        self.assertTrue(any('Incorrect stock SELinux source' in error for error in audit(self.root)))
        path.write_text(original.replace('//system/sepolicy:__subpackages__', '//device/samsung/a23:__pkg__'))
        self.assertTrue(any('Platform cannot read' in error for error in audit(self.root)))

    def test_changed_ownership_patch_is_rejected(self):
        path = self.device / 'patches/sepolicy' / PATCH_NAME
        path.write_bytes(path.read_bytes() + b'\n# unreviewed change\n')
        self.assertTrue(any('differs from source-lock.json' in error for error in audit(self.root)))

    def test_stale_odm_policy_and_digest_are_rejected(self):
        output = self.staged_output()
        odm_out = output / 'odm/etc/selinux'
        (odm_out / 'precompiled_sepolicy').write_bytes(b'old Samsung policy')
        self.assertTrue(any('obsolete stock' in error for error in audit_outputs(self.root, output)))
        (odm_out / 'precompiled_sepolicy').write_bytes(b'new compiled platform plus stock vendor')
        (odm_out / 'precompiled_sepolicy.plat_sepolicy_and_mapping.sha256').write_text('0' * 64)
        self.assertTrue(any('Stale or incorrect' in error for error in audit_outputs(self.root, output)))

    def test_current_platform_changed_after_digest_generation_is_rejected(self):
        output = self.staged_output()
        (output / 'system/etc/selinux/plat_sepolicy.cil').write_text('changed current policy\n')
        self.assertTrue(any('Stale or incorrect' in error for error in audit_outputs(self.root, output)))

    def test_context_reformatting_is_allowed_but_lost_entries_are_rejected(self):
        output = self.staged_output()
        path = output / 'vendor/etc/selinux/vendor_file_contexts'
        path.write_text('# generated comment\n/vendor/bin/fixture\t u:object_r:vendor_fixture_exec:s0\n')
        self.assertEqual(audit_outputs(self.root, output), [])
        path.write_text('# context was accidentally dropped\n')
        self.assertTrue(any('lose or change stock entries' in error for error in audit_outputs(self.root, output)))

    def test_system_ext_merged_into_system_uses_actual_mapping_digest(self):
        output = self.staged_output()
        source = output / 'system_ext'
        destination = output / 'system/system_ext'
        source.resolve().relative_to(self.root.resolve())
        destination.resolve().relative_to(self.root.resolve())
        source.rename(destination)
        self.assertEqual(audit_outputs(self.root, output), [])
        (destination / 'etc/selinux/mapping/30.0.cil').write_text('changed map\n')
        self.assertTrue(any('Stale or incorrect' in error for error in audit_outputs(self.root, output)))

    def test_mac_permission_signer_order_is_ignored_but_rules_are_preserved(self):
        output = self.staged_output()
        source = self.stock / 'vendor_mac_permissions.xml'
        staged = output / 'vendor/etc/selinux/vendor_mac_permissions.xml'
        first = '<signer signature="00"><seinfo value="first"/></signer>'
        second = '<signer signature="11"><seinfo value="second"/></signer>'
        source.write_text('<policy>' + first + second + '</policy>')
        staged.write_text('<policy>' + second + first + '</policy>')
        self.assertEqual(audit_outputs(self.root, output), [])
        staged.write_text('<policy>' + first + '</policy>')
        self.assertTrue(any('MAC permissions differ' in error for error in audit_outputs(self.root, output)))

    def test_exact_reverse_context_refuses_server_edits(self):
        hunks = [(2, 2, ['old'], ['new', 'added'])]
        self.assertEqual(reverse_patch('start\nnew\nadded\nend\n', hunks), 'start\nold\nend\n')
        with self.assertRaisesRegex(ValueError, 'context differs'):
            reverse_patch('start\nnew\nserver edit\nend\n', hunks)


if __name__ == '__main__':
    unittest.main()
