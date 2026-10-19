#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Static checks for the A23 tree. Needs no Android checkout or compiler.

    python3 device/samsung/a23/tools/preflight.py [--root <android root>]
"""
import argparse
import hashlib
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

STOCK_DTB = '064a8b777cebdff6c075f552b3ec6aa92ebb7af663bd3bcd240cb1afebf9b1f3'
STOCK_DTBO = '7d9c005109e3e9524425a70d46b85ccd5c63b732f3d820be4942d3115ea5aa85'
KERNEL_REVISION = '9eec76ce9a2dbbe2707ae5f240b1c028601e78d2'
SUPER_GROUP_SIZE = 9013559296
STOCK_VENDOR_SIZE = 922710016
STOCK_ODM_SIZE = 21389312

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_vars(path):
    """Simple ':=' / '+=' assignments, enough for this tree's makefiles."""
    values = {}
    text = path.read_text().replace('\\\n', ' ')
    for name, operator, value in re.findall(r'^\s*([A-Z0-9_]+)\s*(:=|\+=)\s*(.*)$', text, re.M):
        value = ' '.join(value.split())
        values[name] = (values.get(name, '') + ' ' + value).strip() if operator == '+=' else value
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    root = pathlib.Path(parser.parse_args().root)
    device = root / 'device/samsung/a23'
    vendor = root / 'vendor/samsung/a235f'

    board = make_vars(device / 'BoardConfig.mk')
    check(sha256(device / 'prebuilt/dtb/a23.dtb') == STOCK_DTB, 'DTB is not the SEZB1 one')
    check(sha256(device / 'prebuilt/dtbo.img') == STOCK_DTBO, 'DTBO is not the SEZB1 one')
    check(board.get('BOARD_BOOT_HEADER_VERSION') == '2', 'boot header must be v2')
    for name, value in (('BOARD_KERNEL_OFFSET', '0x00008000'), ('BOARD_RAMDISK_OFFSET', '0x02000000'),
                        ('BOARD_KERNEL_TAGS_OFFSET', '0x01e00000'), ('BOARD_DTB_OFFSET', '0x01f00000'),
                        ('BOARD_KERNEL_PAGESIZE', '4096')):
        check(board.get(name) == value, f'{name} differs from the stock boot image')
    check(board.get('BOARD_QTI_DYNAMIC_PARTITIONS_SIZE') == str(SUPER_GROUP_SIZE), 'super group size')
    partitions = board.get('BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST', '').split()
    check(sorted(partitions) == ['odm', 'product', 'system', 'vendor'], 'dynamic partition list')
    check(board.get('TARGET_OTA_ALLOW_NON_AB') == 'true', 'non-A/B OTA must be allowed explicitly')
    # Prebuilt vendor/odm have no target-files trees; without device block
    # diffs the generic non-A/B script asserts on the super partition list.
    check(board.get('TARGET_RELEASETOOLS_EXTENSIONS') == '$(DEVICE_PATH)', 'releasetools extension not set')
    releasetools = (device / 'releasetools.py').read_text()
    check("STOCK_PARTITIONS = ('vendor', 'odm')" in releasetools, 'releasetools must write vendor and odm')

    config = device / board.get('TARGET_KERNEL_CONFIG_EXT', '').replace('$(DEVICE_PATH)/', '')
    check(config.is_file(), 'kernel config fragment missing')
    manifest = ET.parse(device / 'manifest/a23.xml').getroot()
    kernel = [p for p in manifest.iter('project') if p.get('path') == 'kernel/samsung/a23']
    check(len(kernel) == 1 and kernel[0].get('revision') == KERNEL_REVISION, 'kernel pin')

    # First-stage fstab: one entry per logical partition, matching image types.
    rows = [line.split() for line in (device / 'rootdir/etc/fstab.default').read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]
    logical = {row[1].lstrip('/'): row[2] for row in rows if 'logical' in row[4]}
    check(set(logical) == set(partitions), 'fstab logical partitions differ from the super list')
    check(logical.get('system') == board.get('BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE'), 'system fs type')
    check(logical.get('product') == board.get('BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE'), 'product fs type')
    check(logical.get('vendor') == 'f2fs' and logical.get('odm') == 'f2fs', 'stock vendor/odm are f2fs')
    for mount in ('/boot', '/recovery', '/dtbo', '/data', '/metadata'):
        check(any(row[1] == mount for row in rows), f'fstab lacks {mount}')
    check(not any('avb' in row[4] for row in rows), 'AVB is disabled; drop avb fstab flags')

    # Every top-level mount point of the stock vendor fstab must exist in the
    # AOSP root; anything else (e.g. /mnt/vendor/*) init creates at runtime.
    extra = set(board.get('BOARD_ROOT_EXTRA_FOLDERS', '').split())
    stock_fstab = (vendor / 'reference/fstab.default').read_text().splitlines()
    builtin = {'cache': 'BOARD_CACHEIMAGE_FILE_SYSTEM_TYPE', 'metadata': 'BOARD_USES_METADATA_PARTITION'}
    for line in stock_fstab:
        fields = line.split()
        if len(fields) < 2 or line.lstrip().startswith('#') or not fields[1].startswith('/'):
            continue
        top = fields[1].split('/')[1]
        if top in ('system', 'vendor', 'product', 'odm', 'data', 'mnt', 'misc'):
            continue
        check(top in extra or board.get(builtin.get(top, ''), ''), f'no root mount point for /{top}')

    # Patches the build script applies.
    for directory in ('kernel', 'sepolicy', 'vndk', 'vintf', 'connectivity', 'core'):
        check(any((device / 'patches' / directory).glob('*.patch')), f'no {directory} patches')
    script = (device / 'build_a23.sh').read_text()
    for repository in ('packages/modules/vndk', 'system/sepolicy', 'hardware/interfaces',
                       'kernel/configs', 'packages/modules/Connectivity', 'system/core',
                       'kernel/samsung/a23'):
        check(f'apply_series {repository} ' in script, f'build script does not patch {repository}')

    for path in (device / 'overlay').rglob('*.xml'):
        try:
            ET.parse(path)
        except ET.ParseError as error:
            errors.append(f'{path}: {error}')

    # Stock images: every part listed, sizes match the SEZB1 super layout.
    sums = dict(reversed(line.split()) for line in (vendor / 'images/SHA256SUMS').read_text().splitlines())
    for name in sums:
        if '.xz.' in name:
            check((vendor / 'images' / name).is_file(), f'missing {name}')
            check((vendor / 'images' / name).stat().st_size < 100 * 1024 * 1024, f'{name} exceeds GitHub limit')
    for image, size in (('vendor.img', STOCK_VENDOR_SIZE), ('odm.img', STOCK_ODM_SIZE)):
        check(image in sums, f'{image} checksum missing')
        path = vendor / 'images' / image
        if path.is_file():
            check(path.stat().st_size == size and sha256(path) == sums[image], f'{image} differs from stock')
    check((vendor / 'reference/selinux/plat_sepolicy_vers.txt').read_text().strip() == '30.0',
          'stock vendor policy is expected to be 30.0')

    for message in errors:
        print('ERROR:', message)
    print(f'preflight: {len(errors)} error(s); static checks only, not a build or boot test')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
