#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Public-source entrypoint for an ordinary queued Crave build, cnb / depth 1.

set -Eeuo pipefail

[[ "${A23_REMOTE_BUILD:-}" == 1 && "$(uname -s)" == Linux ]] || {
    echo "Run only on the designated Linux build server with A23_REMOTE_BUILD=1" >&2
    exit 2
}
if grep -qi microsoft /proc/sys/kernel/osrelease; then
    echo "Local Windows/WSL compilation is not permitted for this project" >&2
    exit 2
fi
[[ -f .repo/manifest.xml ]] || {
    echo "Run from the existing Crave Android source root; do not create a nested checkout." >&2
    exit 2
}

readonly EVO_MANIFEST="https://github.com/Evolution-X/manifest.git"
readonly EVO_BRANCH="cnb"
readonly CRAVE_RESYNC="/opt/crave/resync.sh"

BUILD_JOBS="${BUILD_JOBS:-12}"
[[ "$BUILD_JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_JOBS must be a positive integer' >&2; exit 2; }
DEVICE_REVISION="${A23_DEVICE_REVISION:?Pass the published device commit}"
VENDOR_REVISION="${A23_VENDOR_REVISION:?Pass the published vendor commit}"
[[ "$DEVICE_REVISION" =~ ^[0-9a-f]{40}$ && "$VENDOR_REVISION" =~ ^[0-9a-f]{40}$ ]] || exit 2

fail() {
    echo "BUILD_STATUS=FAILED stage=$1" >&2
    exit 1
}

STAGE=initialization
trap 'rc=$?; echo "BUILD_STATUS=FAILED stage=$STAGE source=${BASH_SOURCE[0]} line=$LINENO exit=$rc" >&2; exit "$rc"' ERR

command -v repo >/dev/null || fail "repo-tool-missing"
command -v git >/dev/null || fail "git-missing"
command -v python3 >/dev/null || fail "python3-missing"
[[ -x "$CRAVE_RESYNC" ]] || fail "crave-resync-missing"

# Evolution's environment requires a real ccache executable. Do this before
# syncing, so a missing package cannot waste another complete sync attempt.
STAGE=ccache-setup
if ! command -v ccache >/dev/null; then
    command -v apt-get >/dev/null || fail "ccache-missing-no-package-manager"
    if [[ $(id -u) == 0 ]]; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ccache
    elif command -v sudo >/dev/null && sudo -n true; then
        sudo -n apt-get update
        sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ccache
    else
        fail "ccache-missing-contact-crave-admin"
    fi
fi
export CCACHE_EXEC="$(command -v ccache)"
"$CCACHE_EXEC" --version

git ls-remote --exit-code --heads "$EVO_MANIFEST" "refs/heads/$EVO_BRANCH" >/dev/null


STAGE=repo-init
repo init \
    -u "$EVO_MANIFEST" \
    -b "$EVO_BRANCH" \
    --git-lfs \
    --depth=1 \
    --no-clone-bundle

mkdir -p .repo/local_manifests
cat > .repo/local_manifests/a23.xml <<MANIFEST
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <remote name="a23-github" fetch="https://github.com" />
  <remote name="a23-aosp" fetch="https://android.googlesource.com" />
  <project path="prebuilts/vndk/v30" name="platform/prebuilts/vndk/v30" remote="a23-aosp" revision="5f9884aa352825291757dfd6694b874ad8c1805e" upstream="main" clone-depth="1" />
  <project path="hardware/samsung" name="LineageOS/android_hardware_samsung" remote="a23-github" revision="lineage-24.0" clone-depth="1" />
  <project path="device/samsung/a23" name="hertebeznat-cell/android_device_samsung_a23" remote="a23-github" revision="$DEVICE_REVISION" clone-depth="1" />
  <project path="vendor/samsung/a235f" name="hertebeznat-cell/android_vendor_samsung_a235f" remote="a23-github" revision="$VENDOR_REVISION" clone-depth="1" />
  <project path="kernel/samsung/a23" name="blxyzY/android_kernel_samsung_sm6225" remote="a23-github" revision="8c34b1fc1e921fcac33e839f7d6e9f3ea732221b" upstream="master" clone-depth="1" />
</manifest>
MANIFEST

# Seeded caches can contain copied hooks directories where repo expects a
# shared link. Repair only those references before force-sync can recreate
# an otherwise intact checkout. Fetch this helper from the same public commit.
STAGE=repo-hook-repair
readonly HOOK_REPAIR_SHA256="76aeecd295165d829a4f2dc98fed403ed9e924454bf8a0743ac08b2ffd283e9c"
python3 - "$DEVICE_REVISION" "$HOOK_REPAIR_SHA256" <<'HOOK_REPAIR'
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

revision, expected = sys.argv[1:]
url = ("https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/"
       + revision + "/tools/repair_repo_hooks.py")
for attempt in range(3):
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            source = response.read(1000001)
        break
    except OSError:
        if attempt == 2:
            raise
        time.sleep(5)
if len(source) > 1000000 or hashlib.sha256(source).hexdigest() != expected:
    raise SystemExit("BUILD_STATUS=FAILED stage=repo-hook-helper-sha256")
with tempfile.NamedTemporaryFile(prefix="a23-repo-hooks-", suffix=".py", delete=False) as stream:
    stream.write(source)
    helper = Path(stream.name)
try:
    subprocess.run([sys.executable, str(helper), "--root", os.getcwd(), "--apply"], check=True)
finally:
    helper.unlink(missing_ok=True)
HOOK_REPAIR

# Crave's supported synchronizer resolves checkout conflicts in the seeded
# workspace without manual deletion of platform projects.
STAGE=repo-sync
SYNC_LOG="$(mktemp /tmp/a23-resync.XXXXXX.log)"
"$CRAVE_RESYNC" 2>&1 | tee "$SYNC_LOG"
# Some revisions of resync.sh can return zero after a failed piped repo sync.
# Require repo's own final success message, not the wrapper's optimistic text.
grep -Fq 'repo sync has finished successfully.' "$SYNC_LOG" || fail "repo-sync-incomplete-see-$SYNC_LOG"

STAGE=source-revisions
[[ "$(git -C device/samsung/a23 rev-parse HEAD)" == "$DEVICE_REVISION" ]] || fail "device-revision-mismatch"
[[ "$(git -C vendor/samsung/a235f rev-parse HEAD)" == "$VENDOR_REVISION" ]] || fail "vendor-revision-mismatch"
echo "DEVICE_REVISION=$DEVICE_REVISION"
echo "VENDOR_REVISION=$VENDOR_REVISION"
# Use the same guarded build pipeline for Crave and an already synced server.
# It preserves build logs/patches/checksums locally and never uploads artifacts.
export BUILD_JOBS
exec bash device/samsung/a23/server_build.sh
