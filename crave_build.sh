#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Normal Crave build entrypoint for project 93 (LOS 22.1 image). Not a Devspace.

set -Eeuo pipefail

readonly EVO_MANIFEST="https://github.com/Evolution-X/manifest.git"
readonly EVO_BRANCH="cnb"
readonly DEVICE_REMOTE="https://github.com/hertebeznat-cell/android_device_samsung_a23.git"
readonly VENDOR_REMOTE="https://github.com/hertebeznat-cell/android_vendor_samsung_a235f.git"
readonly KERNEL_REMOTE="https://github.com/hertebeznat-cell/android_kernel_samsung_a235f.git"

SYNC_JOBS="${SYNC_JOBS:-8}"
BUILD_JOBS="${BUILD_JOBS:-12}"

fail() {
    echo "BUILD_STATUS=FAILED stage=$1" >&2
    exit 1
}

trap 'fail "line-$LINENO"' ERR

command -v repo >/dev/null || fail "repo-tool-missing"
command -v git >/dev/null || fail "git-missing"
command -v curl >/dev/null || fail "curl-missing"
command -v python3 >/dev/null || fail "python3-missing"

git ls-remote --exit-code --heads "$EVO_MANIFEST" "refs/heads/$EVO_BRANCH" >/dev/null

# Crave reuses the project workspace between jobs.  The LOS seed checkout can
# contain generated or LFS-smudged files which block Evolution X from switching
# revisions.  Reset only that remote build workspace before changing manifests.
if [[ -f .repo/manifest.xml ]]; then
    repo forall -c '
        git reset --hard HEAD >/dev/null 2>&1 || true
        git clean -ffdx >/dev/null 2>&1 || true
    ' || true

    # repo forall only visits projects from the currently selected manifest.
    # The LOS seed can leave this old Clang checkout outside that manifest, so
    # repo cannot remove it while switching to Evolution X.
    rm -rf -- \
        prebuilts/clang/host/linux-x86 \
        .repo/projects/prebuilts/clang/host/linux-x86.git \
        .repo/project-objects/platform/prebuilts/clang/host/linux-x86.git
fi

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
  <remove-project name="vendor_gms" optional="true" />
  <remove-project name="vendor_gms-mosey" optional="true" />
  <project path="device/samsung/a23" name="hertebeznat-cell/android_device_samsung_a23" remote="a23-github" revision="main" clone-depth="1" />
  <project path="vendor/samsung/a235f" name="hertebeznat-cell/android_vendor_samsung_a235f" remote="a23-github" revision="main" clone-depth="1" />
  <project path="kernel/samsung/a23" name="hertebeznat-cell/android_kernel_samsung_a235f" remote="a23-github" revision="main" clone-depth="1" />
</manifest>
MANIFEST

sync_attempt=1
while ! repo sync \
    -c \
    --force-sync \
    --no-clone-bundle \
    --no-tags \
    --optimized-fetch \
    --prune \
    --force-checkout \
    --force-remove-dirty \
    -j"$SYNC_JOBS"; do
    if (( sync_attempt >= 3 )); then
        fail "repo-sync"
    fi
    echo "repo sync attempt $sync_attempt failed; cleaning worktrees before retry" >&2
    repo forall -c '
        git reset --hard HEAD >/dev/null 2>&1 || true
        git clean -ffdx >/dev/null 2>&1 || true
    ' || true
    rm -rf -- \
        prebuilts/clang/host/linux-x86 \
        .repo/projects/prebuilts/clang/host/linux-x86.git \
        .repo/project-objects/platform/prebuilts/clang/host/linux-x86.git
    sync_attempt=$((sync_attempt + 1))
    sleep 30
done

source build/envsetup.sh
export EVO_BUILD_TYPE=Unofficial
export WITH_GMS=false
lunch lineage_a23-cp2a-userdebug
m -j"$BUILD_JOBS" evolution

ZIP_PATH="$(find out/target/product/a23 -maxdepth 1 -type f -name '*.zip' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
[[ -n "$ZIP_PATH" && -s "$ZIP_PATH" ]] || fail "artifact-not-found"

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
