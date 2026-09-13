#!/usr/bin/env python3
"""Targeted source regressions; no compiler, make, network or checkout mutation."""
import argparse
from pathlib import Path
import re


def without_comments(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def audit(kernel):
    errors = []

    def read(name):
        path = kernel / name
        if not path.is_file():
            errors.append(f'Missing kernel source: {name}')
            return ''
        return path.read_text(encoding='utf-8')

    for name in ('include/linux/vmpressure.h', 'mm/vmpressure.c'):
        declaration = re.search(r'\bvoid\s+vmpressure\s*\(([^)]*)\)', without_comments(read(name)))
        if not declaration or len(declaration[1].split(',')) != 6 or declaration[1].split(',')[-1].strip() != 'int order':
            errors.append(f'{name}: expected the pinned six-argument vmpressure API')
    vmscan = without_comments(read('mm/vmscan.c'))
    calls = re.findall(r'\bvmpressure\s*\(([^;{}]*)\)\s*;', vmscan)
    if len(calls) != 2:
        errors.append(f'Expected two vmscan vmpressure call sites, found {len(calls)}')
    for call in calls:
        args = [item.strip() for item in call.split(',')]
        if len(args) != 6 or args[-1] != 'sc->order':
            errors.append('vmpressure call must have six arguments ending in sc->order')
    subtree = [call for call in calls if 'sc->target_mem_cgroup' in call]
    if len(subtree) != 1:
        errors.append('Subtree vmpressure must be accounted exactly once per reclaim pass')
    elif vmscan.find(subtree[0]) > vmscan.find('sc->nr_reclaimed += reclaim_state->reclaimed_slab'):
        errors.append('Subtree vmpressure must exclude reclaimed slab pages')

    factory = kernel / 'drivers/adsp_factory'
    if not factory.is_dir():
        errors.append('ADSP factory sources missing')
    # Declarations/definitions, not zero-argument call expressions.
    prototype = re.compile(r'^\s*(?:static\s+)?(?:inline\s+)?(?:void|int|bool|ssize_t|unsigned\s+int)\s+(\w+)\s*\(\s*\)\s*(?:\{|;)', re.M)
    for path in sorted(factory.glob('*.[ch]')):
        for match in prototype.finditer(without_comments(path.read_text(encoding='utf-8'))):
            errors.append(f'{path.name}: {match[1]} needs an explicit void prototype')

    header = read('include/uapi/linux/sched/types.h')
    if '#if defined(__ANDROID__) && !defined(__KERNEL__)\n#include <sched.h>\n#else' not in header:
        errors.append('Android sched_param UAPI guard missing')
    engine_guard = '#if OPENSSL_VERSION_NUMBER < 0x40000000L && !defined(OPENSSL_NO_ENGINE) && !defined(OPENSSL_NO_DEPRECATED_3_0)'
    for path in ('scripts/sign-file.c', 'scripts/extract-cert.c'):
        if engine_guard not in read(path):
            errors.append(f'{path}: optional OpenSSL ENGINE guard missing')
    touch = read('drivers/input/touchscreen/st/fts_lib/ftsIO.c')
    for declaration in ('struct device *getDev(void)', 'struct i2c_client *getClient(void)'):
        if declaration not in touch:
            errors.append(f'Touchscreen definition must match header: {declaration}')
    camera = read('techpack/camera/drivers/cam_ope/ope_hw_mgr/cam_ope_hw_mgr.c')
    if 'static int cam_ope_mgr_hw_close_u(void *hw_priv, void *hw_close_args)' not in camera:
        errors.append('Camera close callback needs explicit int return type')
    audio = read('techpack/audio/asoc/codecs/tas256x/os_layer/src/tas256x-regmap.c')
    if '\n\t\t\tkfree(p_tas256x->devs[i]);' in audio or '\n\t\tkfree(p_tas256x->devs);' in audio:
        errors.append('TAS256x remove cleanup has misleading indentation')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    failures = audit(args.kernel)
    for failure in failures:
        print('ERROR:', failure)
    print(f'Kernel source regression checks: {len(failures)} error(s). Not a compile or boot test.')
    raise SystemExit(bool(failures))
