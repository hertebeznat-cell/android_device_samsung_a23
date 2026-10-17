#!/usr/bin/env python3
"""Restore only the A23's removed FCM 5 / R 4.19 inputs on the build server.

No network access, compilation, vendor relabeling or compatibility-check bypass.
The public upstream requirements are carried in two reviewed, hash-locked patches.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

PATCHES = Path(__file__).resolve().parents[1] / 'patches/vintf'


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def added_files(patch):
    """Read complete new-file payloads; never treat context as added input."""
    files = {}
    current = None
    for line in patch.read_text(encoding='utf-8').splitlines():
        if line.startswith('diff --git '):
            current = None
        elif line.startswith('--- /dev/null'):
            current = ''
        elif line.startswith('+++ b/') and current == '':
            current = line[6:]
            files[current] = []
        elif current and line.startswith('+'):
            files[current].append(line[1:] + '\n')
    return {path: ''.join(lines).encode() for path, lines in files.items()}


def metadata():
    return json.loads((PATCHES / 'sources.json').read_text(encoding='utf-8'))


def git_env(root):
    env = os.environ.copy()
    # A fixture/source subdirectory must never silently resolve to a parent
    # checkout: git apply can otherwise skip every path and still return zero.
    env['GIT_CEILING_DIRECTORIES'] = str(Path(root).resolve())
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
        env.pop(key, None)
    return env


def audit(root, server=False):
    root = Path(root).resolve()
    lock = metadata()
    errors = []
    payloads = {}
    for repository in lock['repositories']:
        patch = PATCHES / repository['patch']
        digest = hashlib.sha256(patch.read_bytes()).hexdigest()
        if digest != repository['patch_sha256']:
            errors.append(f'VINTF patch hash differs: {patch.name}')
        files = added_files(patch)
        payloads.update(files)
        for path, data in files.items():
            if blob(data) != repository['after'].get(path):
                errors.append(f'Restored input differs from reviewed upstream blob: {path}')
        if server:
            for path, expected in repository['after'].items():
                target = root / repository['path'] / path
                if not target.is_file() or blob(target.read_bytes()) != expected:
                    errors.append(f'Missing/changed restored VINTF input: {repository["path"]}/{path}')
    matrix = ET.fromstring(payloads['compatibility_matrices/compatibility_matrix.5.xml'])
    if matrix.get('level') != '5' or len(matrix.findall('hal')) < 50:
        errors.append('FCM 5 must retain the full nonempty legacy HAL contract')
    requirements = {
        'android.hardware.audio': '6.0',
        'android.hardware.camera.provider': '2.4-6',
        'android.hardware.radio': '1.5',
    }
    for name, version in requirements.items():
        if not any(hal.findtext('name') == name and
                   version in [value.text for value in hal.findall('version')]
                   for hal in matrix.findall('hal')):
            errors.append(f'FCM 5 lost {name} {version}')
    base = payloads['r/android-4.19/android-base.config'].decode()
    for required in ('CONFIG_ANDROID_BINDER_IPC=y', 'CONFIG_ANDROID_BINDERFS=y',
                     'CONFIG_SECURITY_SELINUX=y', 'CONFIG_BPF_SYSCALL=y'):
        if required not in base.splitlines():
            errors.append(f'R 4.19 kernel contract lost {required}')
    conditional = ET.fromstring(b'<requirements>' +
        payloads['r/android-4.19/android-base-conditional.xml'] + b'</requirements>')
    if conditional.find('kernel').get('minlts') != '4.19.110':
        errors.append('R 4.19 minimum LTS requirement changed')
    if server:
        text = (root / 'hardware/interfaces/compatibility_matrices/Android.bp').read_text()
        for branch in ('A17', 'A18'):
            deps = re.search(r'SYSTEM_MATRIX_DEPS_' + branch + r' = \[(.*?)\]', text, re.S)
            if deps is None or '"framework_compatibility_matrix.5.xml"' not in deps.group(1):
                errors.append(f'FCM 5 is not installed in {branch} system matrix dependencies')
    return errors


def apply_restoration(root):
    """Used by the guarded server CLI and by disposable, non-building tests."""
    root = Path(root).resolve()
    errors = audit(root)
    if errors:
        raise RuntimeError('\n'.join(errors))
    pending = []
    # Validate every repository before changing the first one.
    for repository in metadata()['repositories']:
        checkout = root / repository['path']
        actual = {name: blob((checkout / name).read_bytes()) if (checkout / name).is_file()
                  else None for name in repository['before']}
        if actual == repository['after']:
            continue
        if actual != repository['before']:
            raise RuntimeError(f'Unreviewed VINTF input or local edits in {repository["path"]}; preserve and review them')
        patch = PATCHES / repository['patch']
        subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', str(patch)], cwd=checkout,
                       env=git_env(root), check=True)
        pending.append((checkout, patch))
    for checkout, patch in pending:
        subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', str(patch)], cwd=checkout,
                       env=git_env(root), check=True)
    errors = audit(root, server=True)
    if errors:
        raise RuntimeError('\n'.join(errors))
    return len(pending)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--server', action='store_true', help='Also check restored server inputs')
    args = parser.parse_args()
    if args.apply:
        release = platform.release().lower()
        if (platform.system() != 'Linux' or 'microsoft' in release or
                os.environ.get('A23_REMOTE_BUILD') != '1' or
                not (args.root / '.repo').is_dir()):
            parser.error('--apply requires the synced Linux build server and A23_REMOTE_BUILD=1')
        count = apply_restoration(args.root)
        print(f'VINTF legacy requirements ready ({count} patches applied); compatibility checks remain enabled.')
    else:
        errors = audit(args.root, server=args.server)
        for error in errors:
            print('ERROR:', error)
        if not errors:
            print('VINTF restoration provenance and requirements passed; no compilation or downloads.')
        sys.exit(bool(errors))
