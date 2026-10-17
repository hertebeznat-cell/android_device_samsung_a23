"""Check the VNDK patch against the reviewed Android 17 blob, without compiling.

The existing Android 16 fixture has the identical Git blob ID to Android 17 r1.
Use it offline by default; --revision also accepts the synced server tag.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repository', type=Path)
parser.add_argument('--revision', default='f2caada6c9378ba37879c5b952fab07cf0f46e16',
                    help='Existing local fixture ref; never fetches source')
args = parser.parse_args()
revision = args.revision
device = Path(__file__).resolve().parents[1]
lock = json.loads((device / 'source-lock.json').read_text())
source = subprocess.check_output(['git', '-C', str(args.repository.resolve()),
                                  'show', revision + ':apex/Android.bp'])
blob_id = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
assert blob_id == lock['vndk_apex_bp_blob'], (blob_id, lock['vndk_apex_bp_blob'])
assert b'"com.android.vndk.v30"' not in source
signing_inputs = {
    'apex_manifest.json': '08ad49c0c6a452cf3f690c9ab4abb9eb08230f05',
    'com.android.vndk.pubkey': 'f408d2b49459ffb03185ee9b60dbf1a3b71a1b44',
    'com.android.vndk.pem': '8e71ede0d1a490347f93bdb89b28054961c7408c',
    'com.android.vndk.x509.pem': 'a6e9352f55880d936528e6daa6e16d617eee5dd1',
    'com.android.vndk.pk8': '9eaa0da22e62739ae0f725d7f68b3cd3711321f5',
}
for name, expected in signing_inputs.items():
    actual = subprocess.check_output(['git', '-C', str(args.repository.resolve()),
                                     'rev-parse', revision + ':apex/' + name]).decode().strip()
    assert actual == expected, (name, actual, expected)
patch = device / 'patches/vndk/0001-restore-vndk30-apex.patch'
with tempfile.TemporaryDirectory(prefix='a23-vndk-test-') as temporary:
    root = Path(temporary)
    environment = os.environ.copy()
    # A fixture below a workspace Git repository must behave as a standalone
    # directory. Otherwise git apply silently skips paths outside its prefix.
    environment['GIT_CEILING_DIRECTORIES'] = str(root.resolve().parent)
    (root / 'apex').mkdir()
    (root / 'apex/Android.bp').write_bytes(source)
    for options in (['--check'], [], ['--reverse', '--check']):
        subprocess.run(['git', 'apply', *options, str(patch)], cwd=root,
                       env=environment, check=True)
    result = (root / 'apex/Android.bp').read_text()
    for version in range(30, 35):
        assert result.count(f'name: "com.android.vndk.v{version}"') == 1
    block = re.search(r'apex_vndk\s*\{\s*name: "com.android.vndk.v30",(.*?)\}', result, re.S)[1]
    assert 'defaults: ["vndk-apex-defaults"]' in block
    assert 'vndk_version: "30"' in block
    assert 'system_ext_specific: true' in block
print(f"PASS: {lock['platform_tag']} Git blob and signing inputs match the offline fixture;")
print('patch application/reverse check, unique APEX 30-34; no compilation or downloads.')
