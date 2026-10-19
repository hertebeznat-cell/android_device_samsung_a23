"""Workflow regressions using tiny files and shell stubs; never runs a compiler."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from check_build_config import audit


DEVICE = Path(__file__).resolve().parents[1]
WORKSPACE = DEVICE.parents[2]
BASH = (Path('C:/Program Files/Git/bin/bash.exe') if os.name == 'nt'
        else Path(shutil.which('bash') or '/missing-bash'))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='a23-workflow-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.device = self.root / 'device/samsung/a23'
        self.device.mkdir(parents=True)
        for name in ('server_build.sh', 'crave_build.sh', 'build_a23.sh',
                     'AndroidProducts.mk', 'extract-files.sh', 'setup-makefiles.sh',
                     'lineage.dependencies', 'source-lock.json', 'tools/repair_repo_hooks.py'):
            (self.device / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DEVICE / name, self.device / name)
        self.lock = json.loads((DEVICE / 'source-lock.json').read_text())
        (self.root / 'local_manifests').mkdir()
        manifest = re.search(r'cat > \.repo/local_manifests/a23\.xml <<MANIFEST\n(.*?)\nMANIFEST',
                             (self.device / 'crave_build.sh').read_text(), re.S)
        self.assertIsNotNone(manifest, 'Published Crave entrypoint must contain its local manifest')
        (self.root / 'local_manifests/evolution-a23.xml').write_text(manifest[1], encoding='utf-8')

    def test_reviewed_workflow_is_consistent(self):
        self.assertEqual(audit(self.root, self.device, self.lock), [])
        path = self.device / 'server_build.sh'
        original = path.read_text()
        mutations = (
            original.replace('STAGE=recovery-selinux-validation', 'STAGE=swap')
            .replace('STAGE=vndk-snapshot-validation', 'STAGE=recovery-selinux-validation')
            .replace('STAGE=swap', 'STAGE=vndk-snapshot-validation'),
            original.replace('m -j"$BUILD_JOBS" sepolicy.recovery', 'm -j"$BUILD_JOBS" kernel'),
        )
        for changed in mutations:
            with self.subTest(mutation=changed != original):
                path.write_text(changed)
                self.assertTrue(any('reviewed command' in error or 'reviewed order' in error
                                    for error in audit(self.root, self.device, self.lock)))
        path.write_text(original)

    def test_cts_policy_patch_must_apply_to_cts_before_preflight(self):
        path = self.device / 'server_build.sh'
        original = path.read_text()
        command = 'apply_series cts "$device/patches/cts"'
        block = 'STAGE=cts-sepolicy-compatibility-patches\n' + command + '\n'
        mutations = (
            original.replace(command, ''),
            original.replace(command, 'apply_series system/sepolicy "$device/patches/cts"'),
            original.replace(block, '').replace('STAGE=preflight\n', 'STAGE=preflight\n' + block),
        )
        for changed in mutations:
            with self.subTest(mutation=changed != original):
                path.write_text(changed)
                self.assertTrue(any('CTS SELinux' in error or 'Compatibility patches' in error
                                    for error in audit(self.root, self.device, self.lock)))
        path.write_text(original)

    def test_hook_repair_cannot_be_omitted_moved_or_changed(self):
        path = self.device / 'crave_build.sh'
        original = path.read_text()
        for changed in (original.replace('STAGE=repo-hook-repair', 'STAGE=omitted'),
                        original.replace('STAGE=repo-hook-repair', 'STAGE=swap')
                        .replace('STAGE=repo-sync', 'STAGE=repo-hook-repair')
                        .replace('STAGE=swap', 'STAGE=repo-sync')):
            with self.subTest(mutation=changed != original):
                path.write_text(changed)
                self.assertTrue(any('repair hook references' in item
                                    for item in audit(self.root, self.device, self.lock)))
        path.write_text(original)
        helper = self.device / 'tools/repair_repo_hooks.py'
        helper.write_text(helper.read_text() + '\n# unexpected edit\n')
        self.assertTrue(any('published SHA256' in item for item in audit(self.root, self.device, self.lock)))

    def test_old_platform_lunch_is_rejected(self):
        path = self.device / 'server_build.sh'
        path.write_text(path.read_text().replace(self.lock['lunch'], 'lineage_a23-bp4a-userdebug'))
        self.assertTrue(any('Server lunch differs' in error for error in audit(self.root, self.device, self.lock)))

    def test_missing_legacy_snapshot_is_rejected(self):
        path = self.root / 'local_manifests/evolution-a23.xml'
        import xml.etree.ElementTree as ET
        tree = ET.parse(path)
        for project in tree.getroot().findall('project'):
            if project.get('path') == 'prebuilts/vndk/v30':
                tree.getroot().remove(project)
        tree.write(path, encoding='utf-8')
        self.assertTrue(any('require one project at prebuilts/vndk/v30' in error
                            for error in audit(self.root, self.device, self.lock)))

    def test_all_entrypoints_refuse_without_explicit_remote_opt_in(self):
        if not BASH.is_file():
            self.skipTest('Native Bash unavailable; do not use WSL for these checks')
        environment = os.environ.copy()
        environment.pop('A23_REMOTE_BUILD', None)
        environment.pop('BASH_ENV', None)
        for name in ('build_a23.sh', 'server_build.sh', 'crave_build.sh'):
            with self.subTest(entrypoint=name):
                result = subprocess.run([str(BASH), f'device/samsung/a23/{name}'], cwd=self.root,
                                        env=environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('A23_REMOTE_BUILD=1', result.stdout + result.stderr)
        self.assertFalse((self.root / 'a23-logs').exists())

    def run_server_stub(self, envsetup):
        """Only stub functions run; every compiler/build function is a sentinel."""
        if not BASH.is_file():
            self.skipTest('Native Bash unavailable; do not use WSL for these checks')
        (self.root / 'build').mkdir()
        (self.root / 'build/envsetup.sh').write_text(envsetup, encoding='utf-8')
        (self.root / '.repo').mkdir()
        (self.root / '.repo/manifest.xml').write_text('<manifest/>')
        for kind in ('kernel', 'vndk', 'sepolicy', 'cts', 'releasetools'):
            directory = self.device / 'patches' / kind
            directory.mkdir(parents=True)
            (directory / 'fixture.patch').write_text('stub: git never reads this')
        bootstrap = self.root / 'stub-env.sh'
        revision = self.lock['kernel_revision']
        bootstrap.write_text(f'''uname() {{ printf '%s\\n' Linux; }}
grep() {{ return 1; }}
git() {{ case "$*" in *rev-parse*) printf '%s\\n' {revision};; esac; return 0; }}
repo() {{ return 0; }}
python3() {{ if [[ "$1" == -c ]]; then printf '%s\\n' {revision}; fi; return 0; }}
''', encoding='utf-8')
        environment = os.environ.copy()
        environment.update(A23_REMOTE_BUILD='1', BUILD_JOBS='12', BASH_ENV=bootstrap.as_posix())
        result = subprocess.run([str(BASH), 'device/samsung/a23/server_build.sh'], cwd=self.root,
                                env=environment, capture_output=True, text=True, timeout=20)
        self.assertFalse((self.root / 'build-was-called').exists(), result.stdout + result.stderr)
        snapshots = list((self.root / 'a23-logs').glob('integration-*'))
        self.assertEqual(len(snapshots), 1, result.stdout + result.stderr)
        self.assertEqual(json.loads((snapshots[0] / 'source-lock.json').read_text()), self.lock)
        for kind in ('kernel', 'vndk', 'sepolicy', 'cts', 'releasetools'):
            self.assertEqual((snapshots[0] / 'patches' / kind / 'fixture.patch').read_text(),
                             'stub: git never reads this')
        return result

    def test_crave_refuses_nested_checkout_before_packages_or_sync(self):
        if not BASH.is_file():
            self.skipTest('Native Bash unavailable; do not use WSL for these checks')
        bootstrap = self.root / 'stub-crave-env.sh'
        bootstrap.write_text('''uname() { printf '%s\\n' Linux; }
grep() { return 1; }
repo() { touch forbidden-operation; return 97; }
git() { touch forbidden-operation; return 97; }
apt-get() { touch forbidden-operation; return 97; }
sudo() { touch forbidden-operation; return 97; }
''', encoding='utf-8')
        environment = os.environ.copy()
        environment.update(A23_REMOTE_BUILD='1', BASH_ENV=bootstrap.as_posix())
        environment.pop('A23_DEVICE_REVISION', None)
        environment.pop('A23_VENDOR_REVISION', None)
        result = subprocess.run([str(BASH), 'device/samsung/a23/crave_build.sh'], cwd=self.root,
                                env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('existing Crave Android source root', result.stdout + result.stderr)
        self.assertFalse((self.root / 'forbidden-operation').exists())
        self.assertFalse((self.root / '.repo').exists())

    def crave_sync_stub(self, sync_status=0, runtime_supported=True, runtime_changed=False):
        """All external operations are sentinels; no real repo sync is permitted."""
        if not BASH.is_file():
            self.skipTest('Native Bash unavailable; never use WSL')
        runtime = self.root / '.repo/repo/subcmds'
        runtime.mkdir(parents=True)
        (self.root / '.repo/manifest.xml').write_text('<manifest/>')
        (runtime / 'sync.py').write_text('REPO_SKIP_SELF_UPDATE' if runtime_supported else '# fixture')
        (self.device / 'server_build.sh').write_text('touch "$PWD/server-was-called"\n',
                                                   encoding='utf-8', newline='\n')
        bootstrap = self.root / 'stub-sync-env.sh'
        bootstrap.write_text('''uname() { printf '%s\\n' Linux; }
grep() { case "$*" in *microsoft*) return 1;; *) command grep "$@";; esac; }
ccache() { printf '%s\\n' 'ccache fixture'; }
python3() { touch helper-was-called; return 0; }
mktemp() {
  if [[ "$1" == -d ]]; then command mktemp -d "$PWD/${2##*/}";
  else command mktemp "$PWD/${1##*/}"; fi
}
git() {
  case "$*" in
    *pull*|*reset*|*checkout*) touch forbidden-git-operation; return 97;;
    '-C .repo/repo rev-parse HEAD') printf '%040d\\n' 3;;
    '-C .repo/repo diff --binary HEAD')
      if [[ "$TEST_RUNTIME_CHANGED" == 1 && -f repo-sync-was-called ]]; then
        printf '%s\\n' 'unexpected changed runtime';
      else printf '%s\\n' 'preserved local runtime edit'; fi;;
    '-C device/samsung/a23 rev-parse HEAD') printf '%040d\\n' 1;;
    '-C vendor/samsung/a235f rev-parse HEAD') printf '%040d\\n' 2;;
  esac
  return 0
}
repo() {
  if [[ "$1" == init ]]; then touch repo-init-was-called; return 0; fi
  if [[ "$1" == sync ]]; then
    printf '%s\\n' "$*" > repo-sync-was-called
    printf '%s\\n' 'repo sync has finished successfully.'
    return SYNC_STATUS
  fi
  return 98
}
'''.replace('SYNC_STATUS', str(sync_status)), encoding='utf-8', newline='\n')
        environment = os.environ.copy()
        environment.update(A23_REMOTE_BUILD='1', BUILD_JOBS='12', BASH_ENV=bootstrap.as_posix(),
                           A23_DEVICE_REVISION=f'{1:040d}', A23_VENDOR_REVISION=f'{2:040d}',
                           TEST_RUNTIME_CHANGED=str(int(runtime_changed)))
        result = subprocess.run([str(BASH), 'device/samsung/a23/crave_build.sh'], cwd=self.root,
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertFalse((self.root / 'forbidden-git-operation').exists())
        return result

    def test_crave_checked_sync_preserves_runtime_and_delegates(self):
        result = self.crave_sync_stub()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / 'server-was-called').exists())
        arguments = (self.root / 'repo-sync-was-called').read_text()
        self.assertIn('--no-manifest-update', arguments)
        self.assertNotIn('--force-sync', arguments)

    def test_crave_sync_failure_stops_before_server_build(self):
        result = self.crave_sync_stub(sync_status=37)
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertIn('stage=repo-sync', result.stdout + result.stderr)
        self.assertFalse((self.root / 'server-was-called').exists())

    def test_unsupported_runtime_stops_before_init_or_sync(self):
        result = self.crave_sync_stub(runtime_supported=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('repo-runtime-no-self-update-guard', result.stdout + result.stderr)
        self.assertFalse((self.root / 'repo-init-was-called').exists())
        self.assertFalse((self.root / 'helper-was-called').exists())
        self.assertFalse((self.root / 'repo-sync-was-called').exists())

    def test_runtime_changed_during_sync_stops_before_build(self):
        result = self.crave_sync_stub(runtime_changed=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('repo-runtime-edits-changed', result.stdout + result.stderr)
        self.assertFalse((self.root / 'server-was-called').exists())

    def test_envsetup_failure_stops_before_lunch_and_build(self):
        result = self.run_server_stub('lunch() { touch build-was-called; }\n'
                                      'm() { touch build-was-called; }\nreturn 19\n')
        self.assertEqual(result.returncode, 19, result.stdout + result.stderr)
        self.assertIn('stage=envsetup', result.stdout + result.stderr)

    def test_lunch_failure_stops_before_build(self):
        result = self.run_server_stub('lunch() { return 23; }\n'
                                      'm() { touch build-was-called; }\nreturn 0\n')
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertIn('stage=lunch', result.stdout + result.stderr)

    @staticmethod
    def policy_stubs(recovery_status=0, output_status=0):
        """Simulate policy calls; any later build invocation is a failure sentinel."""
        return '''lunch() { export ANDROID_PRODUCT_OUT="$PWD/out/target/product/a23"; }
m() {
    printf '%s\\n' "$*" >> "$PWD/policy-build-calls"
    case "$*" in
        *sepolicy.recovery*) return RECOVERY_STATUS;;
        *com.android.vndk.v30*|*kernelconfig*|*kernel*|*evolution*) touch build-was-called;;
    esac
    return 0
}
python3() {
    if [[ "$*" == *check_selinux_ownership.py*--product-out* ]]; then
        printf '%s\\n' "$*" > "$PWD/policy-output-check-called"
        return OUTPUT_STATUS
    fi
    return 0
}
return 0
'''.replace('RECOVERY_STATUS', str(recovery_status)).replace('OUTPUT_STATUS', str(output_status))

    def test_recovery_policy_failure_stops_before_output_check_and_later_builds(self):
        result = self.run_server_stub(self.policy_stubs(recovery_status=37))
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertIn('stage=recovery-selinux-validation', result.stdout + result.stderr)
        self.assertEqual((self.root / 'policy-build-calls').read_text().splitlines(), [
            '-j12 selinux_policy', '-j12 a23_stock_vendor_policy_compat_test', '-j12 sepolicy.recovery'])
        self.assertFalse((self.root / 'policy-output-check-called').exists())

    def test_staged_policy_failure_stops_before_vndk_kernel_and_rom(self):
        result = self.run_server_stub(self.policy_stubs(output_status=41))
        self.assertEqual(result.returncode, 41, result.stdout + result.stderr)
        self.assertIn('stage=selinux-output-validation', result.stdout + result.stderr)
        self.assertEqual((self.root / 'policy-build-calls').read_text().splitlines(), [
            '-j12 selinux_policy', '-j12 a23_stock_vendor_policy_compat_test', '-j12 sepolicy.recovery'])
        self.assertIn('--product-out', (self.root / 'policy-output-check-called').read_text())


if __name__ == '__main__':
    unittest.main()
