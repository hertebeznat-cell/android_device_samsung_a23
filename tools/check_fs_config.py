#!/usr/bin/env python3
"""Audit SEZB1 OEM identities and on-disk fs-config records without compiling."""
import argparse
import configparser
from pathlib import Path
import struct
import re


def stock_records(path):
    data = path.read_bytes()
    offset = 0
    records = []
    while offset < len(data):
        if len(data) - offset < 16:
            raise ValueError(f'{path}: truncated fs-config header')
        size, mode, uid, gid, caps = struct.unpack_from('<HHHHQ', data, offset)
        if size < 17 or offset + size > len(data):
            raise ValueError(f'{path}: invalid fs-config record length {size}')
        raw = data[offset + 16:offset + size]
        if b'\0' not in raw:
            raise ValueError(f'{path}: unterminated fs-config path')
        name = raw.split(b'\0', 1)[0].decode('utf-8')
        records.append((name, mode, uid, gid, caps))
        offset += size
    return records


def audit(device, vendor):
    errors = []
    config = configparser.ConfigParser(interpolation=None)
    config.read(device / 'config.fs', encoding='utf-8')
    actual = {}
    used_ids = set()
    for section in config.sections():
        if not section.startswith('AID_'):
            continue
        value = int(config[section]['value'], 0)
        name = section[4:].lower()
        if value in used_ids:
            errors.append(f'Duplicate OEM ID {value}')
        used_ids.add(value)
        if not name.startswith('vendor_') or not (2900 <= value <= 2999 or 5000 <= value <= 5999):
            errors.append(f'Unexpected vendor OEM identity {name}={value}')
        actual[name] = value
    for partition in ('vendor', 'odm'):
        etc = vendor / 'proprietary' / partition / 'etc'
        for line in (etc / 'passwd').read_text().splitlines():
            fields = line.split(':')
            if len(fields) != 7 or fields[2] != fields[3]:
                errors.append(f'Unsupported stock passwd entry: {line}')
            elif actual.get(fields[0]) != int(fields[2]):
                errors.append(f'Missing/changed OEM account: {fields[0]}={fields[2]}')
        for line in (etc / 'group').read_text().splitlines():
            fields = line.split(':')
            if len(fields) != 4 or fields[3]:
                errors.append(f'Unsupported stock group entry: {line}')
            elif actual.get(fields[0]) != int(fields[2]):
                errors.append(f'Missing/changed OEM group: {fields[0]}={fields[2]}')
        for kind in ('files', 'dirs'):
            for name, mode, uid, gid, caps in stock_records(etc / f'fs_config_{kind}'):
                if name.startswith('system/vendor/'):
                    continue  # Legacy alias, not part of this dedicated vendor image.
                if name not in config:
                    errors.append(f'Missing stock fs-config rule: {name}')
                    continue
                section = config[name]
                ids = {'AID_SYSTEM': 1000, 'AID_RADIO': 1001, 'AID_BLUETOOTH': 1002, 'AID_GPS': 1021}
                observed = (int(section['mode'], 8), ids.get(section['user']),
                            ids.get(section['group']), int(section['caps'], 0))
                if observed != (mode, uid, gid, caps):
                    errors.append(f'Changed stock permissions/capabilities: {name}: {observed}')
    vendor_mk = (vendor / 'a235f-vendor.mk').read_text(encoding='utf-8')
    if re.search(r'/etc/(?:passwd|group|fs_config_files|fs_config_dirs):', vendor_mk):
        errors.append('Stock account/fs-config tables must not override generated outputs')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--show-stock-paths', action='store_true')
    args = parser.parse_args()
    device = args.root / 'device/samsung/a23'
    vendor = args.root / 'vendor/samsung/a235f'
    if args.show_stock_paths:
        for partition in ('vendor', 'odm'):
            for kind in ('files', 'dirs'):
                path = vendor / f'proprietary/{partition}/etc/fs_config_{kind}'
                for name, mode, uid, gid, caps in stock_records(path):
                    print(f'{name}: mode={mode:04o} uid={uid} gid={gid} caps=0x{caps:x}')
    errors = audit(device, vendor)
    for error in errors:
        print('ERROR:', error)
    print(f'OEM account audit: {len(errors)} error(s).')
    raise SystemExit(bool(errors))
