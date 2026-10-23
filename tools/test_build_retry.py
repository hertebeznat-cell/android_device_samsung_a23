#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real build wrapper with tiny stubs, without Android sources.

Run with Python 3 on Linux or Windows with Git Bash installed. No network,
compiler, vendor images, or full Android checkout is used.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


DEVICE = pathlib.Path(__file__).resolve().parent.parent
POLICY_TARGETS = [
    'secilc', 'plat_sepolicy.cil', 'system_ext_sepolicy.cil',
    'product_sepolicy.cil', 'plat_30.0.cil', '30.0.compat.cil',
    'system_ext_30.0.cil', 'system_ext_30.0.compat.cil',
    'product_30.0.cil',
]


def find_bash():
    if os.name == 'nt':
        for folder in (os.environ.get('ProgramFiles', 'C:/Program Files'),
                       os.environ.get('ProgramW6432', 'C:/Program Files')):
            candidate = pathlib.Path(folder) / 'Git/bin/bash.exe'
            if candidate.is_file():
                return str(candidate)
    return shutil.which('bash')


BASH = find_bash()


@unittest.skipUnless(BASH, 'Bash is required (Git Bash on Windows)')
class BuildRetryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='a23-build-retry-')
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        (self.root / '.repo').mkdir()
        self.write('device/samsung/a23/build_a23.sh',
                   (DEVICE / 'build_a23.sh').read_text(encoding='utf-8'))
        self.write('out/test.zip', '')
        self.write('test-bin/uname', '#!/usr/bin/env bash\necho Linux\n')
        self.write('test-bin/nproc',
                   '#!/usr/bin/env bash\necho "$A23_TEST_NPROC"\n')
        self.write('test-bin/git', '#!/usr/bin/env bash\nexit 0\n')
        self.write('test-bin/python3',
                   '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$PWD/assemble.calls"\n')
        self.write('device/samsung/a23/tools/check_stock_sepolicy.sh',
                   '#!/usr/bin/env bash\necho checked >> "$PWD/policy-check.calls"\n')
        self.write('build/envsetup.sh', r'''
export OUT="$PWD/out"
lunch() { printf '%s\n' "$*" >> "$PWD/lunch.calls"; }
m() {
    local count=0 outcome
    local -a results
    [[ ! -f "$PWD/m.count" ]] || read -r count < "$PWD/m.count"
    printf '%s\n' "$((count + 1))" > "$PWD/m.count"
    printf '%s\t%s\t%s\n' "$*" "${A23_LOW_MEMORY-unset}" \
        "${ALLOW_MISSING_DEPENDENCIES-unset}" >> "$PWD/m.calls"
    IFS=, read -r -a results <<< "$A23_TEST_RESULTS"
    outcome="${results[$count]:-ok}"
    case "$outcome" in
        killed) echo 'soong bootstrap failed: signal:killed'; return 1 ;;
        exit137) echo 'command failed: exit=137'; return 137 ;;
        failure) echo 'error: missing required source file'; return 1 ;;
        ok) echo 'stub target completed'; return 0 ;;
        *) echo "unknown test outcome: $outcome"; return 99 ;;
    esac
}
''')

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
        path.chmod(0o755)

    def run_build(self, results='ok,ok', jobs=None, nproc=12):
        for name in ('m.count', 'm.calls', 'assemble.calls', 'lunch.calls',
                     'policy-check.calls'):
            (self.root / name).unlink(missing_ok=True)
        environment = os.environ.copy()
        for name in ('BUILD_JOBS', 'A23_STOP_AFTER', 'A23_LOW_MEMORY',
                     'ALLOW_MISSING_DEPENDENCIES', 'BASH_ENV', 'ENV'):
            environment.pop(name, None)
        environment.update(A23_TEST_RESULTS=results, A23_TEST_NPROC=str(nproc))
        if jobs is not None:
            environment['BUILD_JOBS'] = str(jobs)
        result = subprocess.run(
            [BASH, '--noprofile', '--norc', '-c',
             'export PATH="$PWD/test-bin:$PATH"; '
             'exec bash device/samsung/a23/build_a23.sh'],
            cwd=self.root, env=environment, capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=30,
        )
        self.output = result.stdout + result.stderr
        call_path = self.root / 'm.calls'
        self.calls = [line.split('\t') for line in
                      call_path.read_text(encoding='utf-8').splitlines()
                      ] if call_path.exists() else []
        for call in self.calls:
            self.assertEqual(call[1:], ['unset', 'unset'], self.output)
        return result

    def assert_calls(self, expected):
        self.assertEqual([call[0].split() for call in self.calls], expected,
                         self.output)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, self.output)
        self.assertIn('A23_BUILD=SUCCESS', self.output)
        self.assertEqual((self.root / 'policy-check.calls').read_text().splitlines(),
                         ['checked'])

    def assert_failure(self, result, stage):
        self.assertNotEqual(result.returncode, 0, self.output)
        self.assertNotIn('A23_BUILD=SUCCESS', self.output)
        self.assertIn('A23_BUILD=FAILED stage=' + stage, self.output)

    def test_default_jobs_are_capped_at_four(self):
        for cores, jobs in ((1, 1), (2, 2), (4, 4), (12, 4)):
            with self.subTest(cores=cores):
                self.assert_success(self.run_build(nproc=cores))
                self.assert_calls([[f'-j{jobs}', *POLICY_TARGETS],
                                   [f'-j{jobs}', 'evolution']])
                self.assertEqual((self.root / 'assemble.calls').read_text().strip(),
                                 'vendor/samsung/a235f/tools/assemble_images.py')
                self.assertEqual((self.root / 'lunch.calls').read_text().strip(),
                                 'lineage_a23-cp2a-userdebug')

    def test_explicit_jobs_override_default(self):
        self.assert_success(self.run_build(jobs=9, nproc=2))
        self.assert_calls([['-j9', *POLICY_TARGETS], ['-j9', 'evolution']])

    def test_stock_kill_retries_identical_targets_with_half_jobs(self):
        for marker in ('killed', 'exit137'):
            with self.subTest(marker=marker):
                self.assert_success(self.run_build(results=f'{marker},ok,ok', jobs=6))
                self.assert_calls([['-j6', *POLICY_TARGETS],
                                   ['-j3', *POLICY_TARGETS], ['-j3', 'evolution']])

    def test_build_kill_retries_evolution_with_half_jobs(self):
        for marker in ('killed', 'exit137'):
            with self.subTest(marker=marker):
                self.assert_success(self.run_build(results=f'ok,{marker},ok', jobs=5))
                self.assert_calls([['-j5', *POLICY_TARGETS],
                                   ['-j5', 'evolution'], ['-j2', 'evolution']])

    def test_one_job_is_retained_during_retry(self):
        self.assert_success(self.run_build(results='killed,ok,killed,ok', jobs=1))
        self.assert_calls([['-j1', *POLICY_TARGETS], ['-j1', *POLICY_TARGETS],
                           ['-j1', 'evolution'], ['-j1', 'evolution']])

    def test_ordinary_failure_does_not_retry(self):
        for results, stage, calls in (
            ('failure', 'stock-sepolicy', [['-j4', *POLICY_TARGETS]]),
            ('ok,failure', 'build', [['-j4', *POLICY_TARGETS], ['-j4', 'evolution']]),
        ):
            with self.subTest(stage=stage):
                self.assert_failure(self.run_build(results=results), stage)
                self.assert_calls(calls)

    def test_second_failure_is_terminal(self):
        for results, stage, calls in (
            ('killed,killed', 'stock-sepolicy',
             [['-j4', *POLICY_TARGETS], ['-j2', *POLICY_TARGETS]]),
            ('ok,killed,exit137', 'build',
             [['-j4', *POLICY_TARGETS], ['-j4', 'evolution'], ['-j2', 'evolution']]),
        ):
            with self.subTest(stage=stage):
                self.assert_failure(self.run_build(results=results), stage)
                self.assert_calls(calls)

    def test_invalid_job_count_fails_before_build(self):
        for jobs in ('0', '-2', 'text', '1.5'):
            with self.subTest(jobs=jobs):
                result = self.run_build(jobs=jobs)
                self.assertNotEqual(result.returncode, 0, self.output)
                self.assertIn('BUILD_JOBS', self.output)
                self.assert_calls([])
                self.assertFalse((self.root / 'assemble.calls').exists(), self.output)


if __name__ == '__main__':
    unittest.main()
