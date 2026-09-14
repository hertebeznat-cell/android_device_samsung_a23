"""Check the VNDK patch on exact Android 16 source without compiling."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repository', type=Path)
args = parser.parse_args()
revision = 'f2caada6c9378ba37879c5b952fab07cf0f46e16'
source = subprocess.check_output(['git', '-C', str(args.repository.resolve()),
                                  'show', revision + ':apex/Android.bp'])
assert b'"com.android.vndk.v30"' not in source
for name in ('apex_manifest.json', 'com.android.vndk.pubkey',
             'com.android.vndk.pem', 'com.android.vndk.x509.pem', 'com.android.vndk.pk8'):
    subprocess.run(['git', '-C', str(args.repository.resolve()), 'cat-file', '-e',
                    revision + ':apex/' + name], check=True)
device = Path(__file__).resolve().parents[1]
patch = device / 'patches/vndk/0001-restore-vndk30-apex.patch'
with tempfile.TemporaryDirectory(prefix='a23-vndk-test-') as temporary:
    root = Path(temporary)
    (root / 'apex').mkdir()
    (root / 'apex/Android.bp').write_bytes(source)
    for options in (['--check'], [], ['--reverse', '--check']):
        subprocess.run(['git', 'apply', *options, str(patch)], cwd=root, check=True)
    result = (root / 'apex/Android.bp').read_text()
    for version in range(30, 35):
        assert result.count(f'name: "com.android.vndk.v{version}"') == 1
    block = re.search(r'apex_vndk\s*\{\s*name: "com.android.vndk.v30",(.*?)\}', result, re.S)[1]
    assert 'defaults: ["vndk-apex-defaults"]' in block
    assert 'vndk_version: "30"' in block
    assert 'system_ext_specific: true' in block
print('PASS: exact android-16.0.0_r4 fixture, patch application/reverse check, unique APEX 30-34; no compilation.')
