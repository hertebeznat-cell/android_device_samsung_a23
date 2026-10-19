"""Reproduce CTS selection and shell behavior with tiny fixtures, never a compiler."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from check_cts_sepolicy import DEVICE, PATCH_NAME, audit, patch_files
from apply_vintf_compat import git_env


BASH = (Path('C:/Program Files/Git/bin/bash.exe') if os.name == 'nt'
        else Path(shutil.which('bash') or '/missing-bash'))


class CtsPolicyTests(unittest.TestCase):
    def setUp(self):
        directory = DEVICE.parents[2] / '.cts-test-tmp'
        directory.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='case-', dir=directory)
        self.addCleanup(lambda: directory.rmdir() if directory.exists() and
                        not any(directory.iterdir()) else None)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.device = self.root / 'device/samsung/a23'
        self.patches = self.device / 'patches/cts'
        self.patches.mkdir(parents=True)
        for name in (PATCH_NAME, 'sources.json'):
            shutil.copyfile(DEVICE / 'patches/cts' / name, self.patches / name)
        shutil.copyfile(DEVICE / 'source-lock.json', self.device / 'source-lock.json')
        self.files = patch_files((self.patches / PATCH_NAME).read_text(encoding='utf-8'))

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')

    def server_sources(self, patched):
        for name, contents in self.files.items():
            self.write(self.root / 'cts' / name, contents[int(patched)])

    def test_exact_original_and_patched_provenance_pass(self):
        self.assertEqual(audit(self.root), [])
        self.server_sources(patched=True)
        self.assertEqual(audit(self.root, server=True), [])

    def test_unapplied_or_edited_server_source_is_rejected(self):
        self.server_sources(patched=False)
        self.assertEqual(sum('not been applied' in item for item in audit(self.root, server=True)), 2)
        self.server_sources(patched=True)
        path = self.root / 'cts/tools/selinux/Android.bp'
        self.write(path, path.read_text() + '\n// unrelated server edit\n')
        self.assertTrue(any('differs from the reviewed patched' in item
                            for item in audit(self.root, server=True)))

    def test_changed_patch_or_missing_provenance_is_rejected(self):
        path = self.patches / PATCH_NAME
        path.write_bytes(path.read_bytes() + b'\n# unexpected edit\n')
        self.assertTrue(any('differs from source-lock' in item for item in audit(self.root)))
        (self.patches / 'sources.json').unlink()
        self.assertTrue(any('inspection failed' in item for item in audit(self.root)))

    def test_unreviewed_selector_or_target_is_rejected(self):
        path = self.patches / 'sources.json'
        metadata = json.loads(path.read_text())
        for field, value in (('target_revision', 'main'), ('selector', 'wrong.selector'),
                             ('policy_inputs', 'vendor_sepolicy.cil')):
            with self.subTest(field=field):
                changed = dict(metadata)
                changed[field] = value
                self.write(path, json.dumps(changed))
                self.assertTrue(any('provenance differs' in item for item in audit(self.root)))

    def test_patch_applies_reverses_and_refuses_unrelated_edits(self):
        self.server_sources(patched=False)
        checkout = self.root / 'cts'
        patch = self.patches / PATCH_NAME

        def git_apply(*arguments):
            return subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', *arguments, str(patch)],
                                  cwd=checkout, env=git_env(self.root), capture_output=True, text=True)

        self.assertEqual(git_apply('--check').returncode, 0)
        self.assertEqual(git_apply().returncode, 0)
        self.assertEqual(audit(self.root, server=True), [])
        self.assertEqual(git_apply('--reverse', '--check').returncode, 0)
        self.assertEqual(git_apply('--reverse').returncode, 0)
        for name, (before, _) in self.files.items():
            self.assertEqual((checkout / name).read_text(), before)
        path = checkout / 'tools/selinux/Android.bp'
        self.write(path, path.read_text().replace('name: "sepolicy-cil-files"', 'name: "server-edit"'))
        self.assertNotEqual(git_apply('--check').returncode, 0)

    def host_test(self, combined, failure=0):
        if not BASH.is_file():
            self.skipTest('Native Bash unavailable; never use WSL')
        directory = self.root / 'host-test'
        directory.mkdir()
        script = directory / 'seamendc-test.sh'
        self.write(script, self.files['tools/selinux/seamendc-test.sh'][1])
        for name, content in {
                'secilc': '''#!/bin/bash
printf 'CALL\\n' >> compiler-calls
printf '%s\\n' "$@" >> compiler-calls
for argument in "$@"; do
  if [[ "$argument" == *.cil && ! -s "$argument" ]]; then exit 43; fi
done
exit "${STUB_SECILC_EXIT:-0}"
''',
                'seamendc': '#!/bin/bash\ntouch seamendc-called\n',
                'searchpolicy': "#!/bin/bash\nprintf 'CALL\\n' >> searchpolicy-calls\nprintf 'identical allow rule\\n'\n",
        }.items():
            path = directory / name
            self.write(path, content)
            path.chmod(0o755)
        policies = (['a23-combined-sepolicy.cil'] if combined else [
            'plat_sepolicy.cil', 'plat_pub_versioned.cil', 'system_ext_sepolicy.cil',
            'product_sepolicy.cil', 'vendor_sepolicy.cil', 'odm_sepolicy.cil'])
        for name in policies:
            self.write(directory / name, '(type fixture)\n')
        environment = os.environ.copy()
        environment.pop('BASH_ENV', None)
        environment['STUB_SECILC_EXIT'] = str(failure)
        result = subprocess.run([str(BASH), script.name], cwd=directory, env=environment,
                                capture_output=True, text=True, timeout=30)
        calls = [part.splitlines() for part in
                 (directory / 'compiler-calls').read_text().split('CALL\n')[1:]]
        return directory, result, calls, policies

    def test_host_test_uses_complete_combined_policy_in_both_compilations(self):
        directory, result, calls, policies = self.host_test(combined=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        for index, call in enumerate(calls):
            self.assertEqual([argument for argument in call if argument.endswith('.cil')],
                             policies + (['test_sepolicy.cil'] if index == 0 else []))
        self.assertTrue((directory / 'seamendc-called').exists())
        self.assertEqual((directory / 'searchpolicy-calls').read_text().splitlines(), ['CALL'] * 4)

    def test_other_products_keep_original_six_policy_inputs(self):
        _, result, calls, policies = self.host_test(combined=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        for index, call in enumerate(calls):
            self.assertEqual([argument for argument in call if argument.endswith('.cil')],
                             policies + (['test_sepolicy.cil'] if index == 0 else []))

    def test_policy_failure_stops_the_host_test(self):
        directory, result, calls, _ = self.host_test(combined=True, failure=37)
        self.assertEqual(result.returncode, 37)
        self.assertEqual(len(calls), 1)
        self.assertFalse((directory / 'seamendc-called').exists())


if __name__ == '__main__':
    unittest.main()
