#!/usr/bin/env python3
"""Read-only bring-up checks. Does not invoke make, compilers, adb or git fetch."""
import argparse
import collections
import hashlib
import json
import posixpath
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from check_kernel_source import audit as audit_kernel_source
from check_fs_config import audit as audit_fs_config
from check_hal_labels import audit as audit_hal_labels
from check_build_config import audit as audit_build_config
from test_sepolicy_patch import audit as audit_sepolicy_patch
from apply_vintf_compat import audit as audit_vintf_compat
from check_selinux_ownership import audit as audit_selinux_ownership

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
vendor_bp = read(vendor / 'Android.bp')
errors.extend(audit_build_config(root, device, lock))
errors.extend(audit_sepolicy_patch(root / 'system/sepolicy' if args.server else None))
errors.extend(audit_vintf_compat(root, server=args.server))
errors.extend(audit_selinux_ownership(root, device, server=args.server))
# The base documents must pass through assemble_vintf, not an independent
# prebuilt installer. Fragment modules under vintf/manifest remain necessary.
for filename, variable in (('manifest.xml', 'DEVICE_MANIFEST_FILE'),
                           ('compatibility_matrix.xml', 'DEVICE_MATRIX_FILE')):
    source = 'vendor/samsung/a235f/proprietary/vendor/etc/vintf/' + filename
    check(bool(re.search(r'^' + variable + r'\s*:=\s*' + re.escape(source) + r'\s*$', board, re.M)),
          f'{filename} must be assembled through {variable}')
    check(not re.search(r'src\s*:\s*"proprietary/vendor/etc/vintf/' + re.escape(filename) + r'"', vendor_bp),
          f'Independent prebuilt installer collides with assembled VINTF {filename}')
    check(source + ':' not in vendor_mk, f'Raw copy bypasses assembled VINTF {filename}')
errors.extend(audit_fs_config(device, vendor))
errors.extend(audit_hal_labels(device, vendor))
vndk_patch = device / 'patches/vndk/0001-restore-vndk30-apex.patch'
check(vndk_patch.is_file(), 'VNDK 30 APEX restoration patch is missing')
sepolicy_patch = device / 'patches/sepolicy/0001-restore-api30-compatibility.patch'
check(sepolicy_patch.is_file(), 'SELinux API 30 compatibility restoration patch is missing')
if sepolicy_patch.is_file():
    check(hashlib.sha256(sepolicy_patch.read_bytes()).hexdigest() == lock['sepolicy_compat_patch_sha256'],
          'SELinux API 30 patch differs from the reviewed source-lock.json digest')
check((device / 'patches/releasetools/0001-preserve-symlinks.patch').is_file(),
      'Non-A/B OTA symlink preservation patch is missing')
legacy_policy_modules = ('plat_30.0.cil', 'system_ext_30.0.cil', 'product_30.0.cil',
                         '30.0.compat.cil', 'system_ext_30.0.compat.cil')
for module in legacy_policy_modules:
    check(bool(re.search(r'^\s+' + re.escape(module) + r'(?:\s*\\)?\s*$', product, re.M)),
          f'Legacy runtime policy module is not selected: {module}')
entrypoint = read(device / 'server_build.sh')
check('STAGE=vndk-compatibility-patches' in entrypoint and
      entrypoint.index('STAGE=vndk-compatibility-patches') < entrypoint.index('STAGE=preflight'),
      'VNDK APEX patch must be applied before server preflight')
for bp in device.rglob('Android.bp'):
    check(not re.search(r'name\s*:\s*"com\.google\.android\.dialer\.support"', read(bp)),
          f'{bp.relative_to(root)} duplicates the GMS dialer support library')
check('TARGET_PREBUILT_KERNEL :=' not in board, 'Stock prebuilt kernel is still selected')
check('TARGET_KERNEL_CONFIG_EXT :=' in board, 'AOSP kernel fragment is not connected')
check(bool(re.search(r'^TARGET_KERNEL_ADDITIONAL_FLAGS\s*:=.*\bCROSS_COMPILE=aarch64-linux-gnu-.*\bCLANG_TRIPLE=aarch64-linux-gnu-', board, re.M)),
      'Kernel 4.19 needs explicit ARM64 CROSS_COMPILE and CLANG_TRIPLE in LLVM-only mode')
check('CROSS_COMPILE_COMPAT=arm-linux-gnueabi-' in board,
      'Compat vDSO needs an explicit ARM32 clang target')
check('PRODUCT_OTA_ENFORCE_VINTF_KERNEL_REQUIREMENTS := true' in product, 'Kernel compatibility check is disabled')
check(not product.rstrip().endswith('\\'), 'Dangling make continuation at end of device.mk')
check(lock['lunch'] in read(device / 'AndroidProducts.mk'), 'Wrong Android release lunch')
check('proprietary/vendor/etc/vintf/manifest.xml' in board, 'Actual vendor HAL manifest is not selected')
vendor_manifest = ET.parse(vendor / 'proprietary/vendor/etc/vintf/manifest.xml').getroot()
vendor_matrix = ET.parse(vendor / 'proprietary/vendor/etc/vintf/compatibility_matrix.xml').getroot()
check(vendor_manifest.get('target-level') == str(lock['vendor_fcm_level']),
      'Vendor FCM level must match the stock baseline, not the Android platform version')
kernel_manifest = vendor_manifest.find('kernel')
check(kernel_manifest is not None and kernel_manifest.get('target-level') == str(lock['vendor_fcm_level']),
      'Kernel FCM declaration differs from stock baseline')
check(vendor_matrix.findtext('vendor-ndk/version') == str(lock['vendor_vndk_version']),
      'Stock VNDK requirement was removed or changed without a validated ABI migration')
check(vendor_matrix.findtext('system-sdk/version') == str(lock['vendor_system_sdk_version']),
      'Stock system SDK requirement was removed or changed')
check(not re.search(r'^\s+(?:manifest_xml_vintf|compatibility_matrix_xml_vintf)\s*\\', vendor_mk, re.M),
      'VINTF base files have two install producers')
check(not re.search(r'^\s+[^#\n]*lib/modules/[^\n]*:', vendor_mk, re.M), 'Stock kernel modules are still installed')

copies = collections.defaultdict(list)
variables = {'DEVICE_PATH': 'device/samsung/a23', 'TARGET_COPY_OUT_VENDOR': 'vendor',
             'TARGET_COPY_OUT_ODM': 'odm', 'TARGET_COPY_OUT_PRODUCT': 'product',
             'TARGET_COPY_OUT_SYSTEM': 'system', 'TARGET_COPY_OUT_SYSTEM_EXT': 'system_ext',
             'TARGET_COPY_OUT_VENDOR_DLKM': 'vendor_dlkm', 'TARGET_COPY_OUT_ODM_DLKM': 'odm_dlkm',
             'TARGET_COPY_OUT_SYSTEM_DLKM': 'system_dlkm',
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
    check(not re.fullmatch(r'(?:system|system_ext|product|vendor|odm|vendor_dlkm|odm_dlkm|system_dlkm)/(?:etc/)?build\.prop', dest),
          f'Raw partition build.prop copy competes with the property generator: {dest}')
odm_input = read(device / 'odm.prop')
odm_feature = re.findall(r'^\s*ro\.vendor\.qti\.va_odm\.support\s*=\s*([^\s#]+)\s*$', odm_input, re.M)
check(odm_feature == ['1'], 'Generated ODM properties must retain exactly one SEZB1 VA ODM support feature')
check(bool(re.search(r'^TARGET_ODM_PROP\s*\+=\s*\$\(DEVICE_PATH\)/odm\.prop\s*$', board, re.M)),
      'Device ODM feature properties must be inputs to the platform property generator')

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
if 'BOARD_VNDK_VERSION := current' in board and lock['vendor_vndk_version'] == 30:
    warnings.append('VNDK 30 is configured for stock blobs alongside current source modules; linker namespaces and mixed ABI still need server validation.')
warnings.append('Full checkvintf, ELF dependency resolution, SELinux compilation and boot tests require the Linux server/device.')
if '/etc/passwd:' in vendor_mk or '/etc/group:' in vendor_mk:
    warnings.append('Stock account databases are copied; migrate OEM IDs before removing duplicate generated passwd/group rules.')
if 'BUILD_BROKEN_DUP_RULES := true' in board:
    warnings.append('Duplicate install rules are tolerated by BoardConfig; this preflight does not resolve source-versus-blob output ownership.')
if args.server:
    policy = root / 'system/sepolicy'
    compat_bp = policy / 'compat/Android.bp'
    compat_text = read(compat_bp) if compat_bp.is_file() else ''
    for module in legacy_policy_modules:
        check(len(re.findall(r'name\s*:\s*"' + re.escape(module) + r'"', compat_text)) == 1,
              f'Platform must define exactly one legacy policy module: {module}')
    for filename in ('30.0.cil', '30.0.compat.cil', '30.0.ignore.cil'):
        check((policy / 'private/compat/30.0' / filename).is_file(),
              f'Legacy platform policy compatibility input is missing: {filename}')
    releasetools = root / 'build/make/tools/releasetools/non_ab_ota.py'
    check(releasetools.is_file() and
          bool(re.search(r'"zip"\s*,\s*tmpfile\s*,\s*"-r"\s*,\s*"-y"', read(releasetools))),
          'Non-A/B OTA releasetools must preserve symlinks with zip -y')
    snapshot = root / 'prebuilts/vndk/v30'
    proc = subprocess.run(['git', '-C', str(snapshot), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    check(proc.returncode == 0 and proc.stdout.strip() == lock['vndk_snapshot_revision'],
          'Missing or wrong VNDK 30 snapshot revision')
    apex_bp = root / 'packages/modules/vndk/apex/Android.bp'
    check(apex_bp.exists() and '"com.android.vndk.v30"' in read(apex_bp),
          'Current VNDK module tree does not define the requested VNDK 30 APEX')
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
    errors.extend(audit_kernel_source(kernel))
    sched_header = kernel / 'include/uapi/linux/sched/types.h'
    check(sched_header.exists() and
          '#if defined(__ANDROID__) && !defined(__KERNEL__)\n#include <sched.h>\n#else' in read(sched_header),
          'Android sched_param UAPI compatibility patch missing')
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
