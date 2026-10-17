#!/usr/bin/env python3
"""Offline patch checks; optional reviewed Android.bp bytes may arrive on stdin.

Never fetches source. Only --base-bp-stdin writes disposable, small fixtures.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from apply_vintf_compat import PATCHES, added_files, apply_restoration, audit, blob, git_env, metadata

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-bp-stdin', action='store_true')
args = parser.parse_args()
assert not audit(Path(__file__).resolve().parents[4])
if args.base_bp_stdin:
    source = sys.stdin.buffer.read()
    lock = metadata()
    assert blob(source) == lock['repositories'][0]['before']['compatibility_matrices/Android.bp']
    workspace = Path(__file__).resolve().parents[4]
    with tempfile.TemporaryDirectory(prefix='.a23-vintf-test-', dir=workspace) as temporary:
        root = Path(temporary)
        assert root.resolve().is_relative_to(workspace)
        interfaces = root / 'hardware/interfaces'
        kernel = root / 'kernel/configs'
        (interfaces / 'compatibility_matrices').mkdir(parents=True)
        kernel.mkdir(parents=True)
        bp = interfaces / 'compatibility_matrices/Android.bp'
        bp.write_bytes(source)
        assert apply_restoration(root) == 2
        assert not audit(root, server=True)
        assert apply_restoration(root) == 0
        for repository in reversed(lock['repositories']):
            checkout = root / repository['path']
            patch = PATCHES / repository['patch']
            subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--reverse', '--check', str(patch)],
                           cwd=checkout, env=git_env(root), check=True)
            subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--reverse', str(patch)],
                           cwd=checkout, env=git_env(root), check=True)
            assert all(not (checkout / path).exists() for path in added_files(patch))
        assert bp.read_bytes() == source
        bp.write_bytes(source + b'// existing server edit\n')
        try:
            apply_restoration(root)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unreviewed server edit was overwritten')
        assert not (kernel / 'r/android-4.19/Android.bp').exists()
    print('PASS: exact cnb base, apply/idempotency/reverse, preserve-edits rejection; no compilation.')
else:
    print('PASS: hash-locked FCM 5 and R 4.19 requirements; no compilation or source downloads.')
