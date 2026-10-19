#!/usr/bin/env python3
"""Check the CTS consumer of stock policy; no downloads or compiler invocations."""
import hashlib
import json
from pathlib import Path

from check_selinux_ownership import git_sha, patch_hunks


DEVICE = Path(__file__).resolve().parents[1]
PATCH_NAME = '0001-select-stock-policy-inputs.patch'
REVISION = 'refs/tags/android-17.0.0_r1'
SOURCE_BLOBS = {
    'tools/selinux/Android.bp': '24f1110f6ed439d59084e9f581faf722944a39fc',
    'tools/selinux/seamendc-test.sh': 'c348c1abbfc58e5c00a33f895c25ba40339d4217',
}
RESULT_BLOBS = {
    'tools/selinux/Android.bp': '62520934bcb47eee9453fa98ae794d0bee992687',
    'tools/selinux/seamendc-test.sh': 'da585144fb0b9078d7c79d5cf318a28cfc27f682',
}


def patch_files(content):
    """The two complete-file hunks allow offline verification of both exact blobs."""
    files = {}
    for name, hunks in patch_hunks(content, SOURCE_BLOBS).items():
        if len(hunks) != 1 or hunks[0][:2] != (1, 1):
            raise ValueError('CTS patch must retain one complete-file hunk per reviewed file')
        _, _, before, after = hunks[0]
        files[name] = ('\n'.join(before) + '\n', '\n'.join(after) + '\n')
    return files


def audit(root, device=None, server=False):
    root = Path(root)
    device = Path(device) if device else root / 'device/samsung/a23'
    errors = []
    try:
        directory = device / 'patches/cts'
        patch = (directory / PATCH_NAME).read_bytes()
        digest = hashlib.sha256(patch).hexdigest()
        lock = json.loads((device / 'source-lock.json').read_text(encoding='utf-8'))
        metadata = json.loads((directory / 'sources.json').read_text(encoding='utf-8'))
        if lock.get('cts_sepolicy_patch_sha256') != digest:
            errors.append('CTS policy patch differs from source-lock.json')
        if (metadata.get('patch') != PATCH_NAME or metadata.get('patch_sha256') != digest or
                metadata.get('source_git_blobs') != SOURCE_BLOBS or
                metadata.get('result_git_blobs') != RESULT_BLOBS or
                metadata.get('target_repository') != 'platform/cts' or
                metadata.get('target_revision') != REVISION or
                metadata.get('selector') != 'a23.use_stock_vendor_policy' or
                metadata.get('policy_inputs') != 'precompiled_sepolicy_srcs' or
                lock.get('cts_sepolicy_revision') != REVISION):
            errors.append('CTS policy patch provenance differs from the reviewed source/selection')
        for name, (before, after) in patch_files(patch.decode('utf-8')).items():
            if git_sha(before) != SOURCE_BLOBS[name] or git_sha(after) != RESULT_BLOBS[name]:
                errors.append(f'CTS policy patch changes an unreviewed input or result: {name}')
            if server:
                actual = git_sha((root / 'cts' / name).read_text(encoding='utf-8'))
                if actual == SOURCE_BLOBS[name]:
                    errors.append(f'CTS policy patch has not been applied: {name}')
                elif actual != RESULT_BLOBS[name]:
                    errors.append(f'CTS policy source differs from the reviewed patched result: {name}')
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        errors.append(f'CTS policy inspection failed: {error}')
    return errors
