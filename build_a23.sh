#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Build Evolution X for the Galaxy A23 4G from a synced cnb tree (Linux only).
#   bash device/samsung/a23/build_a23.sh            # bring-up userdebug build
#   A23_BRINGUP=false bash device/samsung/a23/build_a23.sh
#
set -Eeuo pipefail
trap 'echo "A23_BUILD=FAILED stage=${stage:-init} line=$LINENO" >&2' ERR

[[ -f build/envsetup.sh && -d .repo ]] || { echo "Run from the Android source root" >&2; exit 2; }
[[ "$(uname -s)" == Linux ]] || { echo "Linux build host required" >&2; exit 2; }

# Absolute: apply_series runs git -C inside each repository.
device="$PWD/device/samsung/a23"
jobs="${BUILD_JOBS:-$(nproc)}"

# Apply one patch series; already-applied patches are skipped, so the script
# can be re-run on the same tree.
apply_series() {
    local repository="$1" patch
    shift
    for patch in "$@"; do
        if git -C "$repository" apply --reverse --check "$patch" 2>/dev/null; then
            echo "already applied: $repository $(basename "$patch")"
        else
            git -C "$repository" apply --check "$patch"
            git -C "$repository" apply "$patch"
            echo "applied: $repository $(basename "$patch")"
        fi
    done
}

stage=patches; echo "---- A23 BUILD STEP: patches ($(date -u +%H:%M:%SZ)) ----"
apply_series packages/modules/vndk "$device"/patches/vndk/*.patch
apply_series system/sepolicy "$device"/patches/sepolicy/*.patch
apply_series hardware/interfaces "$device"/patches/vintf/0001-*.patch
apply_series kernel/configs "$device"/patches/vintf/0002-*.patch
apply_series packages/modules/Connectivity "$device"/patches/connectivity/*.patch
apply_series system/core "$device"/patches/core/*.patch
apply_series device/lineage/sepolicy "$device"/patches/lineage-sepolicy/*.patch
apply_series kernel/samsung/a23 "$device"/patches/kernel/*.patch

stage=stock-images; echo "---- A23 BUILD STEP: stock-images ($(date -u +%H:%M:%SZ)) ----"
python3 vendor/samsung/a235f/tools/assemble_images.py

stage=lunch; echo "---- A23 BUILD STEP: lunch ($(date -u +%H:%M:%SZ)) ----"
# envsetup.sh and its m/lunch functions probe with commands that may fail.
# From here on run without errexit/ERR trap and check every step explicitly.
fail() { echo "A23_BUILD=FAILED stage=$stage" >&2; exit 1; }
set +eEu
trap - ERR
source build/envsetup.sh
lunch lineage_a23-cp2a-userdebug || fail

# m output is kept for diagnosis; an OOM-killed step (signal:killed / exit
# 137, as on Crave's free machines) is retried once with a smaller Soong
# graph (A23_LOW_MEMORY in device.mk) and, for compiles, half the jobs.
mlog=$(mktemp /tmp/a23-m.XXXXXX.log)
run_m() { m "$@" 2>&1 | tee "$mlog"; return "${PIPESTATUS[0]}"; }
oom_killed() { grep -qaE 'signal:killed|exit=137' "$mlog"; }
low_memory() {
    export A23_LOW_MEMORY=true ALLOW_MISSING_DEPENDENCIES=true
    echo "---- A23 BUILD STEP: $stage low-memory retry ($(date -u +%H:%M:%SZ)) ----"
}

# Fail fast: compile the stock vendor policy the way init will at boot.
stage=stock-sepolicy; echo "---- A23 BUILD STEP: stock-sepolicy ($(date -u +%H:%M:%SZ)) ----"
policy_targets=(secilc plat_sepolicy.cil system_ext_sepolicy.cil product_sepolicy.cil
                plat_30.0.cil 30.0.compat.cil system_ext_30.0.cil system_ext_30.0.compat.cil
                product_30.0.cil)
if ! run_m -j"$jobs" "${policy_targets[@]}"; then
    oom_killed || fail
    low_memory
    run_m -j"$jobs" "${policy_targets[@]}" || fail
fi
bash "$device"/tools/check_stock_sepolicy.sh || fail

# Validation runs on short-lived machines (tools/colab_check.sh) stop early:
#   A23_STOP_AFTER=stock-sepolicy  Soong graph + boot-time policy compile
#   A23_STOP_AFTER=bootimage       also Kati, kernel and boot.img
case "${A23_STOP_AFTER:-}" in
    stock-sepolicy)
        echo "A23_BUILD=CHECKED stage=stock-sepolicy"
        exit 0 ;;
    bootimage)
        stage=bootimage; echo "---- A23 BUILD STEP: bootimage ($(date -u +%H:%M:%SZ)) ----"
        run_m -j"$jobs" bootimage || fail
        ls -l "$OUT"/boot.img
        echo "A23_BUILD=CHECKED stage=bootimage"
        exit 0 ;;
esac

stage=build; echo "---- A23 BUILD STEP: build ($(date -u +%H:%M:%SZ)) ----"
if ! run_m -j"$jobs" evolution; then
    oom_killed || fail
    low_memory
    jobs=$(( jobs > 2 ? jobs / 2 : 1 ))
    echo "retrying with -j$jobs"
    run_m -j"$jobs" evolution || fail
fi

echo "A23_BUILD=SUCCESS"
ls -l "$OUT"/*.zip
