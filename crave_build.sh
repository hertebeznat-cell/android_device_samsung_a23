#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Crave entry point for the Galaxy A23 4G, run from the project's Android root
# (LOS 22.1 base, re-initialised to Evolution X cnb as in the Crave docs for
# unsupported ROMs). Never uses --clean, rm -rf on the source tree or out/.
#
#   crave run --no-patch -- "curl -fsSL <raw url of this file> -o /tmp/a23.sh && \
#       A23_DEVICE_REVISION=<sha> bash /tmp/a23.sh"
#
set -Eeuo pipefail
trap 'echo "A23_CRAVE=FAILED stage=${stage:-init} line=$LINENO" >&2' ERR

stage=guard
[[ -d .repo && "$(uname -s)" == Linux ]] || { echo "Run from the Crave Android root" >&2; exit 2; }
revision="${A23_DEVICE_REVISION:-cnb-clean}"
raw="https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/$revision"

stage=repo-init
rm -rf .repo/local_manifests
repo init -u https://github.com/Evolution-X/manifest -b cnb --git-lfs --depth=1
mkdir -p .repo/local_manifests
curl -fsSL --retry 3 "$raw/manifest/a23.xml" -o .repo/local_manifests/a23.xml

stage=repo-sync
/opt/crave/resync.sh

stage=verify-sync
for path in device/samsung/a23/build_a23.sh vendor/samsung/a235f/images/SHA256SUMS \
            kernel/samsung/a23/Makefile prebuilts/vndk/v30/arm64/Android.bp build/envsetup.sh; do
    [[ -f "$path" ]] || { echo "missing after sync: $path" >&2; exit 1; }
done
if [[ "$revision" =~ ^[0-9a-f]{40}$ ]]; then
    [[ "$(git -C device/samsung/a23 rev-parse HEAD)" == "$revision" ]] || {
        echo "device/samsung/a23 is not at $revision" >&2; exit 1; }
fi
echo "A23_DEVICE=$(git -C device/samsung/a23 rev-parse HEAD)"
echo "A23_VENDOR=$(git -C vendor/samsung/a235f rev-parse HEAD)"
echo "A23_KERNEL=$(git -C kernel/samsung/a23 rev-parse HEAD)"

# Earlier jobs left their own integration patches in these checkouts. Return
# them to the synced commit so only this tree's patches are applied.
stage=reset-patched-repos
for repository in system/sepolicy system/core cts build/make hardware/interfaces \
                  kernel/configs packages/modules/vndk packages/modules/Connectivity \
                  kernel/samsung/a23; do
    [[ -d "$repository/.git" || -f "$repository/.git" ]] || continue
    git -C "$repository" reset --quiet --hard HEAD
    git -C "$repository" clean -fdq
done

stage=build
A23_BRINGUP="${A23_BRINGUP:-true}" bash device/samsung/a23/build_a23.sh
