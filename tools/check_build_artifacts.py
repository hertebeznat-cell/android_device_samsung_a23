#!/usr/bin/env python3
"""Verify a fresh A23 OTA exists and record hashes. Never uploads artifacts."""
import argparse
import hashlib
from pathlib import Path
import zipfile


def find_ota(product_out, since):
    candidates = []
    for path in product_out.glob('*.zip'):
        if path.stat().st_size == 0 or path.stat().st_mtime < since:
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                metadata = archive.read('META-INF/com/android/metadata').decode('utf-8')
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, UnicodeError):
            continue
        values = dict(line.split('=', 1) for line in metadata.splitlines() if '=' in line)
        if 'a23' in values.get('pre-device', '').split('|'):
            candidates.append(path)
    if not candidates:
        raise ValueError('No fresh A23 OTA ZIP with Android OTA metadata was produced')
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product_out', type=Path)
    parser.add_argument('--since', type=float, required=True)
    parser.add_argument('--checksums', type=Path, required=True)
    args = parser.parse_args()
    try:
        ota = find_ota(args.product_out, args.since)
        images = [args.product_out / name for name in ('boot.img', 'dtbo.img', 'vbmeta.img')]
        for path in images:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f'Required build image is missing or empty: {path}')
        recovery = args.product_out / 'recovery.img'
        if recovery.is_file():
            images.append(recovery)
        lines = []
        for path in [ota, *images]:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            lines.append(f'{digest.hexdigest()}  {path.resolve()}')
        args.checksums.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.exit(1, f'ERROR: {error}\n')
    print(f'ROM_FILE={ota.resolve()}')
    print(f'SHA256SUMS={args.checksums.resolve()}')


if __name__ == '__main__':
    main()
