#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from an already synced, dedicated Evolution X source tree on Linux.
set -Eeuo pipefail
[[ "${A23_REMOTE_BUILD:-}" == 1 && "$(uname -s)" == Linux ]] || {
    echo "Explicit remote-server opt-in required: A23_REMOTE_BUILD=1" >&2
    exit 2
}
if grep -qi microsoft /proc/sys/kernel/osrelease; then
    echo "Do not compile on the Windows PC, including WSL." >&2
    exit 2
fi
[[ -f build/envsetup.sh && -f .repo/manifest.xml ]] || {
    echo "Run from the synced Android source root." >&2
    exit 2
}
BUILD_JOBS="${BUILD_JOBS:-12}"
[[ "$BUILD_JOBS" =~ ^[1-9][0-9]*$ ]] || {
    echo "BUILD_JOBS must be a positive integer" >&2
    exit 2
}

device=device/samsung/a23
STAGE=initialization
trap 'rc=$?; echo "BUILD_STATUS=FAILED stage=$STAGE source=${BASH_SOURCE[0]} line=$LINENO exit=$rc" >&2; exit "$rc"' ERR
mkdir -p a23-logs
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
log_file="$PWD/a23-logs/build-$stamp.log"
exec > >(tee -a "$log_file") 2>&1

# Check the pinned source before modifying it. A matching patch context alone
# does not establish that a different kernel revision is supported.
STAGE=source-revision
kernel_revision=$(python3 -c 'import json; print(json.load(open("device/samsung/a23/source-lock.json"))["kernel_revision"])')
[[ "$(git -C kernel/samsung/a23 rev-parse HEAD)" == "$kernel_revision" ]]

apply_series() {
    local repository="$1" directory="$2" patch
    local patches=("$PWD/$directory"/*.patch)
    [[ -f "${patches[0]}" ]] || {
        echo "No compatibility patches found in $directory" >&2
        return 1
    }
    for patch in "${patches[@]}"; do
        if git -C "$repository" apply --reverse --check "$patch" 2>/dev/null; then
            echo "Already applied: $(basename "$patch")"
        else
            git -C "$repository" apply --check "$patch"
            git -C "$repository" apply "$patch"
        fi
    done
}

STAGE=vndk-compatibility-patches
apply_series packages/modules/vndk "$device/patches/vndk"
STAGE=sepolicy-compatibility-patches
apply_series system/sepolicy "$device/patches/sepolicy"
STAGE=cts-sepolicy-compatibility-patches
apply_series cts "$device/patches/cts"
STAGE=releasetools-compatibility-patches
apply_series build/make "$device/patches/releasetools"
STAGE=vintf-compatibility-patches
python3 "$device/tools/apply_vintf_compat.py" --root "$PWD" --apply
STAGE=kernel-compatibility-patches
apply_series kernel/samsung/a23 "$device/patches/kernel"
STAGE=preflight
python3 "$device/tools/preflight.py" --root "$PWD" --server
integration_directory="a23-logs/integration-$stamp"
mkdir -p "$integration_directory"
cp -R "$device/patches" "$integration_directory/"
cp "$device/source-lock.json" "$integration_directory/"
repo manifest -r -o "a23-logs/manifest-$stamp.xml"
git -C kernel/samsung/a23 diff --binary > "a23-logs/kernel-$stamp.patch"
git -C packages/modules/vndk diff --binary > "a23-logs/vndk-$stamp.patch"
git -C system/sepolicy diff --binary > "a23-logs/sepolicy-$stamp.patch"
git -C cts diff --binary > "a23-logs/cts-sepolicy-$stamp.patch"
git -C build/make diff --binary > "a23-logs/releasetools-$stamp.patch"
git -C hardware/interfaces diff --binary > "a23-logs/vintf-$stamp.patch"
git -C kernel/configs diff --binary > "a23-logs/kernel-requirements-$stamp.patch"

# Android's environment runs probes with nonzero status and reads unset
# variables. Restore failure handling immediately after sourcing it.
STAGE=envsetup
set +eu
trap - ERR
source build/envsetup.sh
env_status=$?
set -Ee -o pipefail
trap 'rc=$?; echo "BUILD_STATUS=FAILED stage=$STAGE source=${BASH_SOURCE[0]} line=$LINENO exit=$rc" >&2; exit "$rc"' ERR
if [[ "$env_status" != 0 ]]; then
    echo "BUILD_STATUS=FAILED stage=$STAGE exit=$env_status" >&2
    exit "$env_status"
fi
export EVO_BUILD_TYPE=Unofficial WITH_GMS=true
STAGE=lunch
lunch lineage_a23-cp2a-userdebug
product_out="${ANDROID_PRODUCT_OUT:?lunch did not set ANDROID_PRODUCT_OUT}"
build_start=$(date +%s)

STAGE=selinux-validation
m -j"$BUILD_JOBS" selinux_policy
STAGE=stock-vendor-selinux-validation
m -j"$BUILD_JOBS" a23_stock_vendor_policy_compat_test
STAGE=recovery-selinux-validation
m -j"$BUILD_JOBS" sepolicy.recovery
STAGE=selinux-output-validation
python3 "$device/tools/check_selinux_ownership.py" --root "$PWD" --server --product-out "$product_out"
STAGE=vndk-snapshot-validation
m -j"$BUILD_JOBS" com.android.vndk.v30
STAGE=kernel-config
m -j"$BUILD_JOBS" kernelconfig
python3 "$device/tools/check_kernel_config.py" "$product_out/obj/KERNEL_OBJ/.config"
STAGE=kernel-compilation
m -j"$BUILD_JOBS" kernel
STAGE=compilation
m -j"$BUILD_JOBS" evolution

STAGE=artifact-verification
python3 "$device/tools/check_build_artifacts.py" "$product_out" \
    --since "$build_start" --checksums "a23-logs/SHA256SUMS-$stamp"
echo "BUILD_STATUS=SUCCESS"
echo "Build completed. Logs and checksums: $PWD/a23-logs"
echo "Images still require device boot and hardware testing."
