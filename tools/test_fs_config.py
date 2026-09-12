#!/usr/bin/env python3
"""Exercise the official AOSP fs-config generator and compare with stock SEZB1."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
from check_fs_config import audit, stock_records

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path.cwd())
parser.add_argument('--generator', type=Path, required=True)
parser.add_argument('--aid-header', type=Path, required=True)
parser.add_argument('--capability-header', type=Path, required=True)
args = parser.parse_args()
device = args.root / 'device/samsung/a23'
vendor = args.root / 'vendor/samsung/a235f'
assert not audit(device, vendor), audit(device, vendor)
for partition in ('vendor', 'odm'):
    for kind in ('passwd', 'group'):
        output = subprocess.check_output([sys.executable, '-B', str(args.generator), kind,
            '--aid-header', str(args.aid_header), '--partition', partition,
            str(device / 'config.fs')], text=True, timeout=30)
        expected = (vendor / f'proprietary/{partition}/etc/{kind}').read_text()
        assert output.splitlines() == expected.splitlines(), f'{partition}/{kind} differs from SEZB1'
        print(f'PASS: {partition}/{kind} matches stock ({len(output.splitlines())} entries)')
    for kind in ('files', 'dirs'):
        with tempfile.TemporaryDirectory(prefix='a23-fs-config-test-') as directory:
            generated = Path(directory) / f'fs_config_{kind}'
            subprocess.run([sys.executable, '-B', str(args.generator), 'fsconfig',
                '--aid-header', str(args.aid_header), '--capability-header', str(args.capability_header),
                '--partition', partition, '--' + kind, '--out_file', str(generated),
                str(device / 'config.fs')], check=True, timeout=30)
            expected = [record for record in stock_records(vendor / f'proprietary/{partition}/etc/fs_config_{kind}')
                        if not record[0].startswith('system/vendor/')]
            actual = stock_records(generated)
            assert sorted(actual) == sorted(expected), f'{partition}/fs_config_{kind} differs: {actual}'
            print(f'PASS: {partition}/fs_config_{kind} preserves {len(actual)} canonical stock rules')
print('No Android or kernel compilation performed.')
