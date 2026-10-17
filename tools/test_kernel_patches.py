#!/usr/bin/env python3
"""Apply patches to disposable exact git blobs, not the user's kernel checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from check_kernel_source import audit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repository', type=Path)
args = parser.parse_args()
device = Path(__file__).resolve().parents[1]
revision = json.loads((device / 'source-lock.json').read_text())['kernel_revision']

def git(*arguments):
    return subprocess.check_output(['git', '-C', str(args.repository.resolve()), *arguments], timeout=60)

patches = sorted((device / 'patches/kernel').glob('*.patch'))
paths = {'include/linux/vmpressure.h', 'mm/vmpressure.c'}
for patch in patches:
    for line in patch.read_text().splitlines():
        if line.startswith('+++ b/'):
            paths.add(line[6:])
paths.update(git('ls-tree', '-r', '--name-only', revision, 'drivers/adsp_factory').decode().splitlines())
with tempfile.TemporaryDirectory(prefix='a23-patch-test-') as directory:
    root = Path(directory)
    environment = os.environ.copy()
    environment['GIT_CEILING_DIRECTORIES'] = str(root.resolve().parent)
    for name in sorted(paths):
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Unsafe patch path: {name}')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git('show', f'{revision}:{name}'))
    before = audit(root)
    assert any('six arguments' in error for error in before), before
    assert any('exactly once' in error for error in before), before
    assert any('print_ssr_history' in error for error in before), before
    assert sum('Touchscreen definition' in error for error in before) == 2, before
    assert any('Camera close callback' in error for error in before), before
    assert any('misleading indentation' in error for error in before), before
    assert sum('Touchscreen explicit prototype missing' in error for error in before) == 2, before
    assert any('Reference temperature result' in error for error in before), before
    for patch in patches:
        for options in (['--check'], [], ['--reverse', '--check']):
            subprocess.run(['git', 'apply', *options, str(patch)], cwd=root,
                           env=environment, check=True, timeout=30)
        print('PASS apply/reverse-check:', patch.name)
    after = audit(root)
    if after:
        raise SystemExit('\n'.join(after))
    print(f'PASS: {len(paths)} exact source fixtures; original regressions detected and patched sources pass.')
    print('No kernel compilation performed.')
