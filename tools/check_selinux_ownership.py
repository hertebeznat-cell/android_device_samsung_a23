#!/usr/bin/env python3
"""Audit SELinux install ownership and, optionally, staged server outputs.

Read-only: this tool never fetches sources, invokes a compiler or changes files.
Source checks do not establish that the Samsung policy compiles or boots.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


DEVICE = Path(__file__).resolve().parents[1]
PATCH_NAME = '0002-select-stock-vendor-policy-owner.patch'
EXPORTS = {
    'a23_stock_plat_pub_versioned_cil': 'plat_pub_versioned.cil',
    'a23_stock_vendor_sepolicy_cil': 'vendor_sepolicy.cil',
    'a23_stock_plat_sepolicy_vers_txt': 'plat_sepolicy_vers.txt',
    'a23_stock_vendor_file_contexts': 'vendor_file_contexts',
    'a23_stock_vendor_hwservice_contexts': 'vendor_hwservice_contexts',
    'a23_stock_vendor_property_contexts': 'vendor_property_contexts',
    'a23_stock_vendor_seapp_contexts': 'vendor_seapp_contexts',
    'a23_stock_vendor_service_contexts': 'vendor_service_contexts',
    'a23_stock_vndservice_contexts': 'vndservice_contexts',
    'a23_stock_vendor_mac_permissions_xml': 'vendor_mac_permissions.xml',
    'a23_stock_vendor_bug_map': 'selinux_denial_metadata',
}
SOURCE_GIT_BLOBS = {
    'Android.bp': '9ff4263ff6762a30d8ef84deb771bfbedc774290',
    'contexts/Android.bp': 'dcaf3b4adfbf7d653d244f8decd0250ae4a955e8',
    'mac_permissions/Android.bp': '16132c6f63ec0ff291723d718ecfd8124470cb96',
    'build/soong/compat_cil.go': 'ea8e0647a4e59a487c94fb1bb273a8bd8f2aa6c6',
}
CONTEXTS = tuple(name for name in EXPORTS.values() if name.endswith('_contexts'))
CACHES = ('precompiled_sepolicy',
          'precompiled_sepolicy.plat_sepolicy_and_mapping.sha256',
          'precompiled_sepolicy.system_ext_sepolicy_and_mapping.sha256',
          'precompiled_sepolicy.product_sepolicy_and_mapping.sha256')


def read(path):
    return path.read_text(encoding='utf-8-sig')


def git_sha(content):
    data = content.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def patch_hunks(content, expected_targets=None):
    """Parse exact unified hunks; refuse unsupported targets and malformed counts."""
    expected_targets = SOURCE_GIT_BLOBS if expected_targets is None else expected_targets
    result = {}
    for section in content.split('diff --git ')[1:]:
        lines = section.splitlines()
        match = re.fullmatch(r'a/(\S+) b/(\S+)', lines[0])
        if not match or match[1] != match[2] or match[1] not in expected_targets:
            raise ValueError('Unexpected SELinux ownership patch target')
        path = match[1]
        if path in result:
            raise ValueError(f'Duplicate SELinux ownership patch target: {path}')
        hunks = []
        index = 1
        while index < len(lines):
            if not lines[index].startswith('@@ '):
                index += 1
                continue
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*', lines[index])
            if not match:
                raise ValueError(f'Invalid SELinux hunk header: {path}')
            old_start, old_count, new_start, new_count = (
                int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            index += 1
            before, after = [], []
            while index < len(lines) and not lines[index].startswith('@@ '):
                line = lines[index]
                if len(before) == old_count and len(after) == new_count:
                    break
                if not line or line[0] not in ' +-':
                    raise ValueError(f'Invalid SELinux hunk body: {path}')
                if line[0] in ' -':
                    before.append(line[1:])
                if line[0] in ' +':
                    after.append(line[1:])
                index += 1
            if len(before) != old_count or len(after) != new_count:
                raise ValueError(f'Invalid SELinux hunk counts: {path}')
            hunks.append((old_start, new_start, before, after))
        if not hunks:
            raise ValueError(f'No SELinux ownership patch hunks: {path}')
        result[path] = hunks
    if set(result) != set(expected_targets):
        raise ValueError('SELinux ownership patch is missing a reviewed source file')
    return result


def reverse_patch(content, hunks):
    lines = content.splitlines()
    for _, start, before, after in reversed(hunks):
        offset = max(start - 1, 0)
        if lines[offset:offset + len(after)] != after:
            raise ValueError('SELinux ownership patch context differs from reviewed source')
        lines[offset:offset + len(after)] = before
    return '\n'.join(lines) + '\n'


def context_entries(content, seapp=False):
    entries = set()
    for line in content.splitlines():
        fields = line.split('#', 1)[0].split()
        if fields:
            entries.add(tuple(sorted(fields) if seapp else fields))
    return entries


def xml_semantics(element):
    return (element.tag, tuple(sorted(element.attrib.items())),
            (element.text or '').strip(), tuple(sorted(xml_semantics(child) for child in element)))


def audit_outputs(root, product_out):
    errors = []
    stock = root / 'vendor/samsung/a235f/proprietary/vendor/etc/selinux'
    vendor_out = product_out / 'vendor/etc/selinux'
    odm_out = product_out / 'odm/etc/selinux'
    try:
        for name in ('plat_pub_versioned.cil', 'vendor_sepolicy.cil', 'plat_sepolicy_vers.txt'):
            if (vendor_out / name).read_bytes() != (stock / name).read_bytes():
                errors.append(f'Staged vendor policy differs from the selected stock input: {name}')
        for name in CONTEXTS:
            staged = context_entries(read(vendor_out / name), seapp=name == 'vendor_seapp_contexts')
            original = context_entries(read(stock / name), seapp=name == 'vendor_seapp_contexts')
            if staged != original:
                errors.append(f'Staged contexts lose or change stock entries: {name}')
        if xml_semantics(ET.fromstring(read(vendor_out / 'vendor_mac_permissions.xml'))) != \
                xml_semantics(ET.fromstring(read(stock / 'vendor_mac_permissions.xml'))):
            errors.append('Staged vendor MAC permissions differ from the selected stock input')
        if (vendor_out / 'selinux_denial_metadata').read_bytes() != \
                (stock / 'selinux_denial_metadata').read_bytes():
            errors.append('Staged vendor denial metadata differs from the selected stock input')
        compiled = (odm_out / 'precompiled_sepolicy').read_bytes()
        old = root / 'vendor/samsung/a235f/proprietary/odm/etc/selinux/precompiled_sepolicy'
        if not compiled or compiled == old.read_bytes():
            errors.append('Staged ODM policy is empty or is the obsolete stock precompiled binary')
        for partition, prefix in (('system', 'plat'), ('system_ext', 'system_ext'), ('product', 'product')):
            policy_dir = product_out / partition / 'etc/selinux'
            if partition != 'system' and not policy_dir.exists():
                # AOSP can stage these partitions inside system when there is no
                # separate image. Follow an existing directory/symlink only.
                policy_dir = product_out / 'system' / partition / 'etc/selinux'
            expected = hashlib.sha256((policy_dir / f'{prefix}_sepolicy.cil').read_bytes() +
                                      (policy_dir / 'mapping/30.0.cil').read_bytes()).hexdigest()
            system_digest = policy_dir / f'{prefix}_sepolicy_and_mapping.sha256'
            odm_digest = odm_out / f'precompiled_sepolicy.{prefix}_sepolicy_and_mapping.sha256'
            for path in (system_digest, odm_digest):
                if read(path).strip() != expected:
                    errors.append(f'Stale or incorrect staged policy digest: {path.relative_to(product_out)}')
    except (OSError, UnicodeError, ET.ParseError) as error:
        errors.append(f'SELinux staged output inspection failed: {error}')
    return errors


def audit(root, device=None, server=False, product_out=None):
    root = Path(root)
    device = Path(device) if device else root / 'device/samsung/a23'
    vendor = root / 'vendor/samsung/a235f'
    errors = []
    try:
        board = read(device / 'BoardConfig.mk')
        active = '\n'.join(line.split('#', 1)[0] for line in board.splitlines())
        flags = re.findall(r'^\s*\$\(call\s+soong_config_set_bool\s*,\s*a23\s*,\s*use_stock_vendor_policy\s*,\s*([^,)]+)\)\s*$', active, re.M)
        untyped = re.search(r'\$\(call\s+soong_config_set\s*,\s*a23\s*,\s*use_stock_vendor_policy\s*,', active)
        if flags != ['true'] or untyped:
            errors.append('Exactly one enabled typed-boolean a23.use_stock_vendor_policy selector is required')
        forbidden = {'vendor/etc/selinux/' + name for name in EXPORTS.values()}
        forbidden.update('odm/etc/selinux/' + name for name in CACHES)
        for path in (device / 'device.mk', vendor / 'a235f-vendor.mk'):
            for number, line in enumerate(read(path).splitlines(), 1):
                line = line.split('#', 1)[0].replace('$(TARGET_COPY_OUT_VENDOR)', 'vendor')
                line = line.replace('$(TARGET_COPY_OUT_ODM)', 'odm').strip().rstrip('\\').strip()
                if line.count(':') == 1 and line.split(':', 1)[1] in forbidden:
                    errors.append(f'Competing stock SELinux copy/install rule: {path.name}:{number}')
        bp = read(vendor / 'Android.bp')
        groups = re.findall(r'\bfilegroup\s*\{(.*?)^\}', bp, re.S | re.M)
        for name, filename in EXPORTS.items():
            blocks = [block for block in groups if re.search(r'\bname\s*:\s*"' + re.escape(name) + '"', block)]
            if len(blocks) != 1:
                errors.append(f'Require exactly one stock SELinux filegroup: {name}')
                continue
            source = 'proprietary/vendor/etc/selinux/' + filename
            srcs = re.search(r'\bsrcs\s*:\s*\[([^\]]*)\]', blocks[0], re.S)
            if not srcs or re.findall(r'"([^"]+)"', srcs[1]) != [source]:
                errors.append(f'Incorrect stock SELinux source for {name}')
            if not (vendor / source).is_file():
                errors.append(f'Missing stock SELinux source: {source}')
            visibility = re.search(r'\bvisibility\s*:\s*\[([^\]]*)\]', blocks[0], re.S)
            if not visibility or '//system/sepolicy:__subpackages__' not in re.findall(r'"([^"]+)"', visibility[1]):
                errors.append(f'Platform cannot read stock SELinux filegroup: {name}')
        if read(vendor / 'proprietary/vendor/etc/selinux/plat_sepolicy_vers.txt').strip() != '30.0':
            errors.append('Selected stock vendor SELinux policy must remain API 30.0')
        patch_dir = device / 'patches/sepolicy'
        patch_bytes = (patch_dir / PATCH_NAME).read_bytes()
        digest = hashlib.sha256(patch_bytes).hexdigest()
        lock = json.loads(read(device / 'source-lock.json'))
        if lock.get('sepolicy_owner_patch_sha256') != digest:
            errors.append('SELinux ownership patch differs from source-lock.json')
        metadata = json.loads(read(patch_dir / 'sources.json'))
        selected = [entry for entry in metadata.get('patches', []) if entry.get('path') == PATCH_NAME]
        if len(selected) != 1 or selected[0].get('sha256') != digest:
            errors.append('SELinux ownership patch provenance digest does not match')
        elif selected[0].get('source_git_blobs') != SOURCE_GIT_BLOBS:
            errors.append('SELinux ownership source blob identities differ from the reviewed upstream')
        elif set(selected[0].get('vendor_exports', [])) != set(EXPORTS):
            errors.append('SELinux ownership provenance is missing selected vendor exports')
        if metadata.get('target_repository') != 'Evolution-X/system_sepolicy' or \
                metadata.get('target_revision') != lock.get('sepolicy_revision'):
            errors.append('SELinux ownership patch targets a different platform revision')
        hunks = patch_hunks(patch_bytes.decode('utf-8'))
        if server:
            source = root / 'system/sepolicy'
            for path, expected in SOURCE_GIT_BLOBS.items():
                content = read(source / path)
                if git_sha(content) == expected:
                    errors.append(f'SELinux ownership patch has not been applied: {path}')
                    continue
                try:
                    original = reverse_patch(content, hunks[path])
                    if git_sha(original) != expected:
                        errors.append(f'SELinux source differs outside reviewed ownership patch: {path}')
                except ValueError as error:
                    errors.append(f'{path}: {error}')
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        errors.append(f'SELinux ownership inspection failed: {error}')
    if product_out is not None:
        errors.extend(audit_outputs(root, Path(product_out)))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEVICE.parents[2])
    parser.add_argument('--server', action='store_true', help='Require the exact applied platform patch')
    parser.add_argument('--product-out', type=Path, help='Inspect images staged by the authorized server build')
    args = parser.parse_args()
    errors = audit(args.root, server=args.server, product_out=args.product_out)
    for error in errors:
        print('ERROR:', error)
    print(f'SELinux ownership audit: {len(errors)} error(s). '
          'Source/output inspection does not replace policy compilation or boot testing.')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
