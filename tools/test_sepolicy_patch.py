#!/usr/bin/env python3
"""Verify the API 30 restoration without fetching sources or compiling policy.

Optionally pass --source PATH_TO_SYSTEM_SEPOLICY to check the exact target
Android.bp, either before or after applying the patch. CIL compilation and
neverallow validation remain mandatory server build stages.
"""
import argparse
import hashlib
from pathlib import Path
import re
import sys


DEVICE = Path(__file__).resolve().parents[1]
PATCH = DEVICE / 'patches/sepolicy/0001-restore-api30-compatibility.patch'
TARGET_BP_SHA = '4bf086c714dc69bb845631e9fc90fee5e5b283df'
# Original Git blob identities at LineageOS/android_system_sepolicy revision
# 885cc500f6078a766d1f6def5ce4c06c55841773. These are not generated substitutes.
INPUTS = {
    'private/compat/30.0/30.0.cil':
        'f95488ccaf4ecd86e83f5b76525c98ae9cbdc418',
    'private/compat/30.0/30.0.compat.cil':
        'c9c5f477dd63420b4c6548c8dfd5773e56c0b294',
    'private/compat/30.0/30.0.ignore.cil':
        '1d3b3892f61f3f3ec59c445f3d775ac80c6733f7',
}
INSTALLED = {
    'plat_30.0.cil', 'system_ext_30.0.cil', 'product_30.0.cil',
    '30.0.compat.cil', 'system_ext_30.0.compat.cil',
}
MODULES = INSTALLED | {
    '30.0.board.compat.map', '30.0.board.compat.cil', '30.0.board.ignore.map',
    '30.0.ignore.cil', 'system_ext_30.0.ignore.cil', 'product_30.0.ignore.cil',
}


def git_sha(content):
    data = content.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def parse_patch(content):
    result = {}
    for section in content.split('diff --git ')[1:]:
        lines = section.splitlines()
        match = re.fullmatch(r'a/(\S+) b/(\S+)', lines[0])
        if not match or match[1] != match[2] or match[1] in result:
            raise ValueError('Unexpected or duplicate patch path')
        path = match[1]
        if path != 'compat/Android.bp' and path not in INPUTS:
            raise ValueError(f'Unexpected patch target: {path}')
        index = next(i for i, line in enumerate(lines) if line.startswith('@@ '))
        hunk = re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', lines[index])
        if hunk is None:
            raise ValueError(f'Invalid hunk header: {path}')
        start, old_count, new_start, new_count = map(int, hunk.groups())
        body = []
        removed = added = 0
        for line in lines[index + 1:]:
            if removed == old_count and added == new_count:
                if line.strip():
                    raise ValueError(f'Unexpected trailing patch data: {path}')
                continue
            if not line or line[0] not in ' +-':
                raise ValueError(f'Invalid hunk body: {path}')
            body.append(line)
            removed += line[0] in ' -'
            added += line[0] in ' +'
        if (removed, added) != (old_count, new_count):
            raise ValueError(f'Incorrect hunk line counts: {path}')
        result[path] = (start, old_count, new_start, new_count, body)
    if set(result) != {'compat/Android.bp', *INPUTS}:
        raise ValueError('Missing restoration file')
    return result


def apply_hunk(content, hunk, reverse=False):
    start, count, new_start, new_count, body = hunk
    if reverse:
        start, count = new_start, new_count
        body = [({'-': '+', '+': '-', ' ': ' '})[line[0]] + line[1:]
                for line in body]
    original = content.splitlines()
    before = [line[1:] for line in body if line[0] in ' -']
    after = [line[1:] for line in body if line[0] in ' +']
    if original[start - 1:start - 1 + count] != before:
        raise ValueError('Patch context does not match')
    return '\n'.join(original[:start - 1] + after + original[start - 1 + count:]) + '\n'


def audit(source=None):
    errors = []
    try:
        hunks = parse_patch(PATCH.read_text(encoding='utf-8'))
        for path, expected in INPUTS.items():
            start, old_count, new_start, _, body = hunks[path]
            if (start, old_count, new_start) != (0, 0, 1):
                raise ValueError(f'Compatibility input is not an added file: {path}')
            content = '\n'.join(line[1:] for line in body) + '\n'
            if git_sha(content) != expected:
                errors.append(f'Original compatibility input changed: {path}')
        added_bp = '\n'.join(line[1:] for line in hunks['compat/Android.bp'][4]
                             if line.startswith('+'))
        modules = re.findall(r'name:\s*"([^"]+)"', added_bp)
        if set(modules) != MODULES or len(modules) != len(MODULES):
            errors.append('Restored module definitions are missing or duplicated')
        for prefix in ('plat_', 'system_ext_', 'product_'):
            block = re.search(r'se_cil_compat_map\s*\{[^}]*name:\s*"' +
                              prefix + r'30\.0\.cil"[\s\S]*?^\}', added_bp, re.M)
            if block is None or f'top_half: "{prefix}31.0.cil"' not in block[0]:
                errors.append(f'{prefix}30.0 mapping is not chained to API 31')
        product = (DEVICE / 'device.mk').read_text(encoding='utf-8')
        packages = set()
        for block in re.finditer(r'^PRODUCT_PACKAGES\s*\+=([^\n]*)',
                                 product.replace('\\\n', ' '), re.M):
            packages.update(block[1].split())
        if not INSTALLED <= packages:
            errors.append('Runtime API 30 mapping modules are not selected')
        bp = (DEVICE / 'Android.bp').read_text(encoding='utf-8')
        if not all(f'":{name}"' in bp for name in INSTALLED):
            errors.append('Stock policy test does not include every runtime compatibility input')
        if source:
            current = (source / 'compat/Android.bp').read_text(encoding='utf-8')
            if git_sha(current) == TARGET_BP_SHA:
                apply_hunk(current, hunks['compat/Android.bp'])
                state = 'before application'
            else:
                original = apply_hunk(current, hunks['compat/Android.bp'], reverse=True)
                if git_sha(original) != TARGET_BP_SHA:
                    raise ValueError('Platform compatibility definitions differ from the reviewed target')
                for path, expected in INPUTS.items():
                    if git_sha((source / path).read_text(encoding='utf-8')) != expected:
                        errors.append(f'Installed platform compatibility input changed: {path}')
                state = 'after application'
            print(f'Exact platform patch context matches {state}.')
    except (OSError, ValueError, StopIteration) as exc:
        errors.append(str(exc))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Existing system/sepolicy checkout')
    args = parser.parse_args()
    errors = audit(args.source)
    for error in errors:
        print(f'ERROR: {error}')
    print(f'API 30 restoration: {len(errors)} source integrity error(s). '
          'Policy compilation and runtime compatibility remain unverified.')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
