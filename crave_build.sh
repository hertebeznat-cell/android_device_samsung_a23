#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Crave entry point for the Galaxy A23 4G, run from the project's Android root
# (LOS 22.1 base, re-initialised to Evolution X cnb as in the Crave docs for
# unsupported ROMs). Never uses --clean, rm -rf on the source tree or out/.
#
#   crave run --no-patch -- "curl -fsSL <raw url of this file> -o /tmp/a23.sh && \
#       A23_DEVICE_REVISION=<sha> A23_VENDOR_REVISION=<sha> bash /tmp/a23.sh"
#
# Progress: every stage prints an "A23 STAGE" banner, and a heartbeat prints an
# "A23_PROGRESS" line every minute with the elapsed time and the latest repo
# (sync) or ninja (build) percentage.
#
set -Eeuo pipefail

started=$(date +%s)
state=/tmp/a23-crave
mkdir -p "$state"
sync_log="$state/sync.log"
build_log="$state/build.log"
: > "$sync_log"
: > "$build_log"

elapsed() { local s=$(( $(date +%s) - started )); printf '%dh%02dm' $((s / 3600)) $((s % 3600 / 60)); }

stage() {
    stage="$1"
    echo "$stage" > "$state/stage"
    echo
    echo "==================== A23 STAGE: $stage  (+$(elapsed), $(date -u +%H:%M:%SZ)) ===================="
}

# Last progress figure of the running stage: repo's "Fetching: 37% (420/1130)"
# or ninja's "[ 45% 12345/67890]".
progress() {
    case "$(cat "$state/stage" 2>/dev/null)" in
        repo-sync)
            tail -c 65536 "$sync_log" 2>/dev/null | tr '\r' '\n' |
                grep -aoE '(Fetching|Checking out|Syncing)[^%]{0,40}[0-9]+% \([0-9]+/[0-9]+\)' | tail -n 1 || true ;;
        build)
            tail -c 65536 "$build_log" 2>/dev/null | tr '\r' '\n' |
                grep -aoE '\[ *[0-9]+% [0-9]+/[0-9]+[^]]*\]' | tail -n 1 || true ;;
    esac
}

heartbeat() {
    # Runs in the background: never trip the job's error handling.
    set +eE
    trap - ERR
    while sleep 60; do
        echo "A23_PROGRESS +$(elapsed) stage=$(cat "$state/stage" 2>/dev/null) $(progress)"
    done
}
heartbeat &
heartbeat_pid=$!
trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT
trap 'echo "A23_CRAVE=FAILED stage=${stage:-init} line=$LINENO elapsed=$(elapsed)" >&2' ERR

stage guard
[[ -d .repo && "$(uname -s)" == Linux ]] || { echo "Run from the Crave Android root" >&2; exit 2; }
device_revision="${A23_DEVICE_REVISION:-main}"
vendor_revision="${A23_VENDOR_REVISION:-}"
raw="https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/$device_revision"

stage repo-init
rm -rf .repo/local_manifests
repo init -u https://github.com/Evolution-X/manifest -b cnb --git-lfs --depth=1
mkdir -p .repo/local_manifests
curl -fsSL --retry 3 "$raw/manifest/a23.xml" -o .repo/local_manifests/a23.xml
# Pin the trees to the exact commits of this job, so pushes to the main
# branches during a long sync cannot change what gets built.
python3 - .repo/local_manifests/a23.xml "$device_revision" "$vendor_revision" <<'PIN'
import re, sys
path, device, vendor = sys.argv[1:4]
text = open(path).read()
for name, sha in (('android_device_samsung_a23', device), ('android_vendor_samsung_a235f', vendor)):
    if re.fullmatch(r'[0-9a-f]{40}', sha):
        text, count = re.subn(r'(name="hertebeznat-cell/%s"[^>]*?revision=")[^"]+"' % name,
                              r'\g<1>%s"' % sha, text, flags=re.S)
        assert count == 1, name
        print(f'pinned {name} to {sha}')
open(path, 'w').write(text)
PIN
cat .repo/local_manifests/a23.xml

stage repo-sync
# repo only draws its progress bar on a terminal; give it one with script(1).
if command -v script >/dev/null; then
    script -qefc /opt/crave/resync.sh "$sync_log"
else
    /opt/crave/resync.sh 2>&1 | tee "$sync_log"
fi

stage verify-sync
for path in device/samsung/a23/build_a23.sh vendor/samsung/a235f/images/SHA256SUMS \
            kernel/samsung/a23/Makefile prebuilts/vndk/v30/arm64/Android.bp build/envsetup.sh; do
    [[ -f "$path" ]] || { echo "missing after sync: $path" >&2; exit 1; }
done
for pair in "device/samsung/a23:$device_revision" "vendor/samsung/a235f:$vendor_revision"; do
    path="${pair%%:*}" sha="${pair#*:}"
    if [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
        [[ "$(git -C "$path" rev-parse HEAD)" == "$sha" ]] || { echo "$path is not at $sha" >&2; exit 1; }
    fi
done
echo "A23_DEVICE=$(git -C device/samsung/a23 rev-parse HEAD)"
echo "A23_VENDOR=$(git -C vendor/samsung/a235f rev-parse HEAD)"
echo "A23_KERNEL=$(git -C kernel/samsung/a23 rev-parse HEAD)"

# The LOS 22.1 base left files of older project revisions behind as untracked
# files (job 306580: Android 15 external/cronet/third_party/**/Android.bp next
# to the Android 17 tot/ and stable/ trees). Soong parses every Android.bp, so
# clean any project that holds untracked build files. Tracked sources and out/
# are untouched; this tree's own projects are skipped.
stage clean-stale-sources
repo forall -j"$(nproc)" -c '
    case "$REPO_PATH" in device/samsung/a23|vendor/samsung/a235f|kernel/samsung/a23) exit 0 ;; esac
    stale=$(git ls-files --others -- "*Android.bp" "*Android.mk" | head -n 3 | tr "\n" " ")
    if [ -n "$stale" ]; then
        echo "A23_STALE $REPO_PATH: $stale"
        git clean -fdxq
    fi
'

# Earlier jobs left their own integration patches in these checkouts. Return
# them to the synced commit so only this tree's patches are applied.
stage reset-patched-repos
for repository in system/sepolicy system/core device/lineage/sepolicy cts build/make hardware/interfaces \
                  kernel/configs packages/modules/vndk packages/modules/Connectivity \
                  kernel/samsung/a23; do
    [[ -d "$repository/.git" || -f "$repository/.git" ]] || continue
    git -C "$repository" reset --quiet --hard HEAD
    git -C "$repository" clean -fdq
    echo "reset $repository to $(git -C "$repository" rev-parse --short HEAD)"
done

stage build
A23_BRINGUP="${A23_BRINGUP:-false}" bash device/samsung/a23/build_a23.sh 2>&1 | tee "$build_log"

stage done
echo "A23_CRAVE=SUCCESS elapsed=$(elapsed)"
