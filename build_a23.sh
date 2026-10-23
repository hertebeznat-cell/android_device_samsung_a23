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
# Crave can expose many CPUs to a container with much less memory. R8 alone
# uses a 4 GiB Java heap; do not start one compile per visible CPU by default.
cpus=$(nproc)
jobs="${BUILD_JOBS:-$(( cpus < 4 ? cpus : 4 ))}"
[[ "$jobs" =~ ^[1-9][0-9]*$ && ${#jobs} -le 6 ]] || {
    echo "BUILD_JOBS must be a positive integer (at most six digits)" >&2
    exit 2
}

memory_snapshot() {
    echo "A23_MEMORY stage=${stage:-init} jobs=$jobs"
    grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo || true
    local file
    for file in /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current \
                /sys/fs/cgroup/memory.events /sys/fs/cgroup/memory.peak \
                /sys/fs/cgroup/memory/memory.limit_in_bytes \
                /sys/fs/cgroup/memory/memory.failcnt; do
        if [[ -r "$file" ]]; then
            echo "A23_MEMORY $file"
            cat "$file" || true
        fi
    done
}

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

# Keep the same product configuration and dependencies on retry. Excluding
# test/app_compat removes the csuite_test plugin used by ART and WM Shell.
# SIGKILL can indicate memory pressure, but is not proof of an OOM kill.
mlog=$(mktemp /tmp/a23-m.XXXXXX.log)
run_m() { m "$@" 2>&1 | tee "$mlog"; return "${PIPESTATUS[0]}"; }
killed_step() { grep -qaE 'signal:killed|exit=137([^0-9]|$)' "$mlog"; }
run_targets() {
    memory_snapshot
    if run_m -j"$jobs" "$@"; then
        return 0
    fi
    memory_snapshot
    killed_step || return 1
    jobs=$(( jobs > 1 ? jobs / 2 : 1 ))
    echo "---- A23 BUILD STEP: $stage SIGKILL retry ($(date -u +%H:%M:%SZ)) ----"
    echo "retrying unchanged targets with -j$jobs: $*"
    if run_m -j"$jobs" "$@"; then
        return 0
    fi
    memory_snapshot
    return 1
}

# Fail fast: compile the stock vendor policy the way init will at boot.
stage=stock-sepolicy; echo "---- A23 BUILD STEP: stock-sepolicy ($(date -u +%H:%M:%SZ)) ----"
policy_targets=(secilc plat_sepolicy.cil system_ext_sepolicy.cil product_sepolicy.cil
                plat_30.0.cil 30.0.compat.cil system_ext_30.0.cil system_ext_30.0.compat.cil
                product_30.0.cil)
run_targets "${policy_targets[@]}" || fail
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
        run_targets bootimage || fail
        ls -l "$OUT"/boot.img
        echo "A23_BUILD=CHECKED stage=bootimage"
        exit 0 ;;
esac

stage=build; echo "---- A23 BUILD STEP: build ($(date -u +%H:%M:%SZ)) ----"
run_targets evolution || fail

echo "A23_BUILD=SUCCESS"
ls -l "$OUT"/*.zip
