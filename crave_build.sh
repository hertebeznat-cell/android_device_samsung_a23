#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Normal Crave build entrypoint for project 93 (LOS 22.1 image). Not a Devspace.

set -Eeuo pipefail

[[ "${A23_REMOTE_BUILD:-}" == 1 && "$(uname -s)" == Linux ]] || {
    echo "Run only on the designated Linux build server with A23_REMOTE_BUILD=1" >&2
    exit 2
}
if grep -qi microsoft /proc/sys/kernel/osrelease; then
    echo "Local Windows/WSL compilation is not permitted for this project" >&2
    exit 2
fi

readonly EVO_MANIFEST="https://github.com/Evolution-X/manifest.git"
readonly EVO_BRANCH="bka"
readonly DEVICE_REMOTE="https://github.com/hertebeznat-cell/android_device_samsung_a23.git"
readonly VENDOR_REMOTE="https://github.com/hertebeznat-cell/android_vendor_samsung_a235f.git"
readonly KERNEL_REMOTE="https://github.com/blxyzY/android_kernel_samsung_sm6225.git"
readonly CRAVE_RESYNC="/opt/crave/resync.sh"

BUILD_JOBS="${BUILD_JOBS:-12}"
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
command -v curl >/dev/null || fail "curl-missing"
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
  <project path="hardware/samsung" name="LineageOS/android_hardware_samsung" remote="a23-github" revision="lineage-23.2" clone-depth="1" />
  <project path="device/samsung/a23" name="hertebeznat-cell/android_device_samsung_a23" remote="a23-github" revision="$DEVICE_REVISION" upstream="evo-11.10-sezb1-gms" clone-depth="1" />
  <project path="vendor/samsung/a235f" name="hertebeznat-cell/android_vendor_samsung_a235f" remote="a23-github" revision="$VENDOR_REVISION" upstream="evo-11.10-sezb1-gms" clone-depth="1" />
  <project path="kernel/samsung/a23" name="blxyzY/android_kernel_samsung_sm6225" remote="a23-github" revision="8c34b1fc1e921fcac33e839f7d6e9f3ea732221b" upstream="master" clone-depth="1" />
</manifest>
MANIFEST

# Crave's supported synchronizer resolves checkout conflicts in the seeded
# workspace without manual deletion of platform projects.
STAGE=repo-sync
SYNC_LOG="$(mktemp /tmp/a23-resync.XXXXXX.log)"
"$CRAVE_RESYNC" 2>&1 | tee "$SYNC_LOG"
# Some revisions of resync.sh can return zero after a failed piped repo sync.
# Require repo's own final success message, not the wrapper's optimistic text.
grep -Fq 'repo sync has finished successfully.' "$SYNC_LOG" || fail "repo-sync-incomplete-see-$SYNC_LOG"

STAGE=preflight
python3 device/samsung/a23/tools/preflight.py --root "$PWD" --server
grep -Eq '^EVO_VERSION_BASE[[:space:]]*:=[[:space:]]*11\.10[[:space:]]*$' vendor/lineage/config/version.mk || fail "unexpected-evo-version"
# Android's environment scripts are not guaranteed to be nounset-safe.
STAGE=envsetup
set +eu
trap - ERR
source build/envsetup.sh
ENV_STATUS=$?
set -e
trap 'rc=$?; echo "BUILD_STATUS=FAILED stage=$STAGE source=${BASH_SOURCE[0]} line=$LINENO exit=$rc" >&2; exit "$rc"' ERR
[[ "$ENV_STATUS" == 0 ]] || fail "envsetup-exit-$ENV_STATUS"
export EVO_BUILD_TYPE=Unofficial
export WITH_GMS=true
STAGE=lunch
lunch lineage_a23-bp4a-userdebug
BUILD_START="$(date +%s)"
STAGE=compilation
m -j"$BUILD_JOBS" evolution

ZIP_PATH="$(python3 - "$BUILD_START" <<'PY'
import pathlib, sys
files = [p for p in pathlib.Path('out/target/product/a23').glob('*.zip')
         if p.stat().st_size and p.stat().st_mtime >= int(sys.argv[1])]
if not files:
    raise SystemExit('No new ROM ZIP produced by this build')
print(max(files, key=lambda p: p.stat().st_mtime))
PY
)"
[[ -n "$ZIP_PATH" && -s "$ZIP_PATH" ]] || fail "artifact-not-found"

STAGE=artifact-upload
SHA256="$(sha256sum "$ZIP_PATH" | cut -d' ' -f1)"
UPLOAD_JSON="$(curl --fail --silent --show-error --retry 3 --retry-all-errors \
    -F "file=@$ZIP_PATH" \
    https://upload.gofile.io/uploadfile)"
DOWNLOAD_URL="$(python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok"; print(d["data"]["downloadPage"])' <<<"$UPLOAD_JSON")"
[[ "$DOWNLOAD_URL" == https://* ]] || fail "artifact-upload"

echo "BUILD_STATUS=SUCCESS"
echo "ROM_FILE=$(basename "$ZIP_PATH")"
echo "SHA256=$SHA256"
echo "DOWNLOAD_URL=$DOWNLOAD_URL"
