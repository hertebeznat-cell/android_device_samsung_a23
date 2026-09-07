#!/usr/bin/env python3
"""Read an already generated kernel .config; never invoke a compiler or make."""
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('config', type=Path)
args = parser.parse_args()
if not args.config.is_file():
    parser.error(f'Generated config does not exist: {args.config}')
values = {}
for line in args.config.read_text(encoding='utf-8').splitlines():
    match = re.fullmatch(r'(CONFIG_\w+)=(.*)', line)
    disabled = re.fullmatch(r'# (CONFIG_\w+) is not set', line)
    if match:
        values[match[1]] = match[2]
    elif disabled:
        values[disabled[1]] = 'n'
required = '''ANDROID_BINDER_IPC ANDROID_BINDERFS CGROUPS CGROUP_PIDS
CGROUP_DEVICE CGROUP_BPF MEMCG PSI BPF BPF_SYSCALL BPF_JIT SECCOMP
SECCOMP_FILTER SECURITY SECURITYFS SECURITY_SELINUX EXT4_FS F2FS_FS
FS_ENCRYPTION F2FS_FS_ENCRYPTION BLK_DEV_DM DM_DEFAULT_KEY
BLK_INLINE_ENCRYPTION FS_ENCRYPTION_INLINE_CRYPT CRYPTO_AES CRYPTO_XTS
QCA_CLD_WLAN IKCONFIG IKCONFIG_PROC PSTORE PSTORE_RAM'''.split()
errors = [f'CONFIG_{name}: expected y, got {values.get("CONFIG_" + name, "absent")}'
          for name in required if values.get('CONFIG_' + name) != 'y']
for name in ('UH', 'RKP', 'KDP', 'KDP_CRED', 'KDP_NS', 'SECURITY_DEFEX',
             'CMDLINE_FORCE', 'SIMPLE_LMK', 'PSI_DEFAULT_DISABLED'):
    if values.get('CONFIG_' + name, 'n') != 'n':
        errors.append(f'CONFIG_{name} must be disabled for this configuration')
if values.get('CONFIG_ANDROID_BINDER_DEVICES') != '"binder,hwbinder,vndbinder"':
    errors.append('Unexpected Binder device configuration')
for error in errors:
    print('ERROR:', error)
print(f'Kernel configuration audit: {len(errors)} error(s). Not an ABI or boot test.')
raise SystemExit(bool(errors))
