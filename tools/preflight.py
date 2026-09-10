#!/usr/bin/env python3
"""Read-only bring-up checks. Does not invoke make, compilers, adb or git fetch."""
import argparse
import collections
import json
import posixpath
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[4])
ap.add_argument('--server', action='store_true')
args = ap.parse_args()
root = args.root.resolve()
device = root / 'device/samsung/a23'
vendor = root / 'vendor/samsung/a235f'
errors = []
warnings = []

def read(path):
    return path.read_text(encoding='utf-8-sig')

def check(ok, message):
    if not ok:
        errors.append(message)

lock = json.loads(read(device / 'source-lock.json'))
board = read(device / 'BoardConfig.mk')
product = read(device / 'device.mk')
vendor_mk = read(vendor / 'a235f-vendor.mk')
for bp in device.rglob('Android.bp'):
    check(not re.search(r'name\s*:\s*"com\.google\.android\.dialer\.support"', read(bp)),
          f'{bp.relative_to(root)} duplicates the GMS dialer support library')
check('TARGET_PREBUILT_KERNEL :=' not in board, 'Stock prebuilt kernel is still selected')
check('TARGET_KERNEL_CONFIG_EXT :=' in board, 'AOSP kernel fragment is not connected')
check('PRODUCT_OTA_ENFORCE_VINTF_KERNEL_REQUIREMENTS := true' in product, 'Kernel compatibility check is disabled')
check(not product.rstrip().endswith('\\'), 'Dangling make continuation at end of device.mk')
check('lineage_a23-bp4a-userdebug' in read(device / 'AndroidProducts.mk'), 'Wrong Android release lunch')
check('proprietary/vendor/etc/vintf/manifest.xml' in board, 'Actual vendor HAL manifest is not selected')
check(not re.search(r'^\s+(?:manifest_xml_vintf|compatibility_matrix_xml_vintf)\s*\\', vendor_mk, re.M),
      'VINTF base files have two install producers')
check(not re.search(r'^\s+[^#\n]*lib/modules/[^\n]*:', vendor_mk, re.M), 'Stock kernel modules are still installed')

copies = collections.defaultdict(list)
variables = {'DEVICE_PATH': 'device/samsung/a23', 'TARGET_COPY_OUT_VENDOR': 'vendor',
             'TARGET_COPY_OUT_ODM': 'odm', 'TARGET_COPY_OUT_PRODUCT': 'product',
             'TARGET_COPY_OUT_RAMDISK': 'root', 'TARGET_COPY_OUT_VENDOR_RAMDISK': 'vendor_ramdisk'}
for name, data in [('device.mk', product), ('a235f-vendor.mk', vendor_mk)]:
    for number, line in enumerate(data.splitlines(), 1):
        line = line.split('#', 1)[0].strip().rstrip('\\').strip()
        for key, value in variables.items():
            line = line.replace('$(' + key + ')', value)
        if not line or len(line.split()) != 1 or line.count(':') != 1:
            continue
        source, dest = line.split(':')
        copies[dest].append(f'{name}:{number} {source}')
        if source.startswith(('device/samsung/', 'vendor/samsung/')):
            check((root / source).exists(), f'Missing copied file: {source}')
for dest, sources in copies.items():
    check(len(sources) == 1, f'Duplicate copy destination {dest}: {sources}')

links = json.loads(read(device / 'vendor-links/links.json'))
seen_links = set()
for link in links:
    path, target = link['path'], link['target']
    check(path not in copies and path not in seen_links, f'Duplicate symlink destination: {path}')
    seen_links.add(path)
    check(path.startswith('vendor/') and posixpath.normpath(path) == path, f'Unsafe symlink path: {path}')
    check(posixpath.normpath(target) == target, f'Unclean symlink target: {target}')
    if not target.startswith('/'):
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        check((vendor / 'proprietary' / resolved).is_file(), f'Missing relative symlink target: {path} -> {resolved}')
check('vendor-links/packages.mk' in product, 'Vendor symlink modules are not included')
check('PRODUCT_PACKAGES += toybox_vendor' in product, 'Source toybox_vendor is not selected')
check('bin/toybox_vendor:' not in vendor_mk, 'Stock toybox collides with source toybox_vendor')
check('vendor/etc/ueventd.rc' in copies, 'Canonical vendor ueventd rules are missing')
check('ueventd.a23.rc' not in product, 'Unimported synthetic ueventd rules selected')

fstab = read(device / 'rootdir/etc/fstab.default')
rows = [line.split() for line in fstab.splitlines() if line.strip() and not line.lstrip().startswith('#')]
for partition in ('system', 'product', 'vendor', 'odm'):
    matches = [r for r in rows if r[0] == partition]
    check(len(matches) == 1 and matches[0][2] == 'ext4', f'{partition} fstab/image filesystem mismatch')
check('emmc_optimized' not in fstab, 'eMMC crypto option used for UFS')
check(any(r[0].endswith('/apnhlos') and r[1] == '/vendor/firmware_mnt' for r in rows), 'Incorrect Qualcomm firmware mount')
check('/by-name/bluetooth' not in fstab, 'Unverified bluetooth partition in fstab')

for path in list(device.rglob('*.xml')) + list((vendor / 'proprietary/vendor/etc/vintf').rglob('*.xml')):
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        errors.append(f'Invalid XML {path.relative_to(root)}: {exc}')

# Detect collisions introduced by device rc files against installed stock rc.
services = collections.defaultdict(list)
for path in (vendor / 'proprietary/vendor/etc/init').rglob('*.rc'):
    for service in re.findall(r'^service\s+(\S+)', read(path), re.M):
        services[service].append(str(path.relative_to(root)))
for path in (device / 'rootdir/etc').glob('*.rc'):
    if path.name not in product:
        continue
    for service in re.findall(r'^service\s+(\S+)', read(path), re.M):
        check(service not in services, f'Duplicate init service {service}: {path.name}, {services[service]}')

vendor_props = read(vendor / 'proprietary/vendor/build.prop')
odm_props = read(vendor / 'proprietary/odm/etc/build.prop')
check('ro.vendor.build.version.incremental=' + lock['vendor_blob_baseline'] in vendor_props,
      'Vendor blob provenance differs from source-lock.json')
check('ro.odm.build.version.incremental=' + lock['vendor_blob_baseline'] in odm_props,
      'ODM blob provenance differs from source-lock.json')
check('ro.vendor.build.security_patch=' + lock['vendor_security_patch'] in vendor_props,
      'Wrong stock vendor security patch')
check('VENDOR_SECURITY_PATCH := ' + lock['vendor_security_patch'] in read(vendor / 'BoardConfigVendor.mk'),
      'Generated vendor security patch differs from stock')
check('bin/install-recovery.sh:' not in vendor_mk and 'init/vendor_flash_recovery.rc:' not in vendor_mk,
      'Stock recovery restoration is still installed')
warnings.append('SEZB1 vendor/DTB baseline is matched; legacy VNDK 30 and source-kernel runtime ABI remain unverified.')
warnings.append('Full checkvintf, ELF dependency resolution, SELinux compilation and boot tests require the Linux server/device.')
if args.server:
    version_file = root / 'vendor/lineage/config/version.mk'
    check(version_file.exists(), 'Evolution X version.mk missing')
    if version_file.exists():
        match = re.search(r'^EVO_VERSION_BASE[ \t]*:=[ \t]*([^\r\n]+)', read(version_file), re.M)
        actual_version = match.group(1).strip() if match else '<missing>'
        expected_version = lock['evolution_version']
        print(f'Evolution X version: expected={expected_version}, actual={actual_version}')
        check(actual_version == expected_version,
              f'Expected Evolution X {expected_version}, found {actual_version}')
    kernel = root / 'kernel/samsung/a23'
    proc = subprocess.run(['git', '-C', str(kernel), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    check(proc.returncode == 0 and proc.stdout.strip() == lock['kernel_revision'], 'Wrong kernel revision')
    check((kernel / 'arch/arm64/configs/a23_eur_open_defconfig').is_file(), 'Incomplete kernel checkout')
    check((root / 'hardware/samsung/Android.bp').exists(), 'Samsung hardware dependency missing')

for warning in warnings:
    print('REQUIRES VALIDATION:', warning)
for error in errors:
    print('ERROR:', error)
print(f'Static preflight: {len(errors)} error(s). This is not a bootability test.')
sys.exit(bool(errors))
