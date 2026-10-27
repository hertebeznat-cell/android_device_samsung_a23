#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Build on a plain x86_64 Debian/Ubuntu machine as root: a rented server or
# Google Colab (needs ~48 GB RAM+swap, ~300 GB disk). Syncs Evolution X cnb with --depth=1 plus
# this tree, then runs build_a23.sh. A23_STOP_AFTER=full (default) builds the
# whole ROM; stock-sepolicy or bootimage stop after those checks. On success the
# OTA zip is copied to Google Drive when /content/drive/MyDrive is mounted.
#
# Server (as root, inside tmux):
#   curl -fsSL https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/<sha>/tools/colab_check.sh -o /root/a23.sh && A23_DEVICE_REVISION=<sha> BUILD_JOBS=12 bash /root/a23.sh
# Colab cell:
#   !curl -fsSL https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/<sha>/tools/colab_check.sh -o /content/a23.sh && A23_DEVICE_REVISION=<sha> bash /content/a23.sh
#
# Work dir and log default to /content/evo and /content/a23-full.log on Colab,
# /srv/a23/evo and /srv/a23/a23-full.log elsewhere. The console only
# shows stages, a progress line per minute and, on failure, the log tail.
set -Eeuo pipefail

if [[ -d /content ]]; then base=/content; else base=/srv/a23; fi
work="${A23_WORK:-$base/evo}"
log="${A23_LOG:-$base/a23-full.log}"
device_revision="${A23_DEVICE_REVISION:-main}"
vendor_revision="${A23_VENDOR_REVISION:-}"
stop_after="${A23_STOP_AFTER:-full}"
raw="https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/$device_revision"

# --- phase 1 (root): packages, repo launcher, unprivileged build user -------
if [[ "${1:-}" != --as-builder ]]; then
    [[ "$(uname -m)" == x86_64 ]] || { echo "x86_64 Linux required" >&2; exit 2; }
    echo "== A23 COLAB: setup ($(date -u +%H:%M:%SZ)) =="
    command -v apt-get >/dev/null || { echo "Debian/Ubuntu (apt-get) required" >&2; exit 2; }
    mkdir -p "$(dirname "$log")" "$work"
    nproc; free -g | sed -n '2,3p'; df -h "$work" | tail -n 1
    # Soong's analysis of the Evolution graph peaks around 40 GB.
    total_gb=$(awk '/^(MemTotal|SwapTotal):/ {kb += $2} END {print int(kb / 1048576)}' /proc/meminfo)
    if (( total_gb < 48 )); then
        echo "WARNING: RAM+swap is ${total_gb} GB; Soong may be OOM-killed. Add swap first, e.g.:"
        echo "  fallocate -l 32G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile"
    fi
    : > "$log"
    export DEBIAN_FRONTEND=noninteractive
    apt-get -qq update >> "$log" 2>&1
    apt-get -qq install -y git git-lfs bc bison flex libssl-dev rsync zip unzip lz4 xz-utils \
        python3 cpio file >> "$log" 2>&1
    curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo -o /usr/local/bin/repo
    chmod 755 /usr/local/bin/repo
    id builder >/dev/null 2>&1 || useradd -m -s /bin/bash builder
    mkdir -p "$work"
    chown builder: "$work"
    chmod 666 "$log"
    script=$(mktemp /tmp/a23-colab.XXXXXX.sh)
    cp "$0" "$script"
    chmod 755 "$script"
    runuser -u builder -- env HOME=/home/builder PATH="/usr/local/bin:$PATH" \
        A23_WORK="$work" A23_LOG="$log" A23_DEVICE_REVISION="$device_revision" \
        A23_VENDOR_REVISION="$vendor_revision" A23_STOP_AFTER="$stop_after" \
        ${BUILD_JOBS:+BUILD_JOBS="$BUILD_JOBS"} \
        bash "$script" --as-builder || exit $?
    # Google Drive is mounted for root only; copy the OTA zip from here.
    if [[ -d /content/drive/MyDrive ]]; then
        for zip in "$work"/out/target/product/a23/*.zip; do
            [[ -f "$zip" ]] && cp "$zip" /content/drive/MyDrive/ && echo "copied to Google Drive: MyDrive/$(basename "$zip")"
        done
    fi
    exit 0
fi

# --- phase 2 (builder) -------------------------------------------------------
started=$(date +%s)
elapsed() { local s=$(( $(date +%s) - started )); printf '%dh%02dm' $((s / 3600)) $((s % 3600 / 60)); }
stage=setup
banner() { stage="$1"; echo "$1" > /tmp/a23-colab-stage; echo "== A23 COLAB: $1 (+$(elapsed), $(date -u +%H:%M:%SZ)) =="; }
heartbeat() {
    set +eE; trap - ERR
    while sleep 60; do
        figure=$(tail -c 65536 "$log" 2>/dev/null | tr '\r' '\n' |
            grep -aoE '(Fetching|Checking out|Syncing)[^%]{0,40}[0-9]+% \([0-9]+/[0-9]+\)|\[ *[0-9]+% [0-9]+/[0-9]+[^]]*\]' | tail -n 1)
        echo "A23_PROGRESS +$(elapsed) stage=$(cat /tmp/a23-colab-stage 2>/dev/null)" \
             "disk_free=$(df -h --output=avail "$work" | tail -n 1 | tr -d ' ')" \
             "mem_avail=$(free -g | awk '/Mem:/ {print $7}')G $figure"
    done
}
heartbeat &
heartbeat_pid=$!
trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT
fail() {
    echo "A23_COLAB=FAILED stage=$stage elapsed=$(elapsed) — last log lines:" >&2
    tail -n 80 "$log" >&2
    exit 1
}
run() { "$@" >> "$log" 2>&1 || fail; }

cd "$work"
git config --global user.name a23-colab
git config --global user.email a23-colab@localhost
git config --global color.ui false
git lfs install --skip-repo >> "$log" 2>&1

banner repo-init
run repo init -u https://github.com/Evolution-X/manifest -b cnb --git-lfs --depth=1 --no-clone-bundle
mkdir -p .repo/local_manifests
run curl -fsSL --retry 3 "$raw/manifest/a23.xml" -o .repo/local_manifests/a23.xml
run python3 - .repo/local_manifests/a23.xml "$device_revision" "$vendor_revision" <<'PIN'
import re, sys
path, device, vendor = sys.argv[1:4]
text = open(path).read()
for name, sha in (('android_device_samsung_a23', device), ('android_vendor_samsung_a235f', vendor)):
    if re.fullmatch(r'[0-9a-f]{40}', sha):
        text, count = re.subn(r'(name="hertebeznat-cell/%s"[^>]*?revision=")[^"]+"' % name,
                              r'\g<1>%s"' % sha, text, flags=re.S)
        assert count == 1, name
open(path, 'w').write(text)
PIN

banner repo-sync
# repo draws its progress ("Fetching: 37% (420/1130)") only on a terminal; run
# it under script(1) so the log, and the progress line above, get it.
sync() {
    local cmd="repo sync -c -j$(nproc) --no-tags --no-clone-bundle --optimized-fetch --force-sync --retry-fetches=3"
    if command -v script >/dev/null; then
        script -qefac "$cmd" "$log" > /dev/null
    else
        $cmd >> "$log" 2>&1
    fi
}
sync || { echo "first sync pass failed, retrying"; sync || fail; }
for path in device/samsung/a23/build_a23.sh vendor/samsung/a235f/images/SHA256SUMS \
            kernel/samsung/a23/Makefile prebuilts/vndk/v30/arm64/Android.bp; do
    [[ -f "$path" ]] || { echo "missing after sync: $path" >> "$log"; fail; }
done
echo "A23_DEVICE=$(git -C device/samsung/a23 rev-parse HEAD)"
echo "A23_KERNEL=$(git -C kernel/samsung/a23 rev-parse HEAD)"
df -h --output=used,avail "$work" | tail -n 1

banner "build-a23 (stop after $stop_after)"
[[ "$stop_after" == full ]] && stop_after=""
A23_STOP_AFTER="$stop_after" A23_BRINGUP=true bash device/samsung/a23/build_a23.sh >> "$log" 2>&1 || {
    grep -a -E "A23 BUILD STEP|A23_BUILD=|STOCK_SEPOLICY" "$log" | tail -n 20 >&2
    fail
}
grep -a -E "A23 BUILD STEP|A23_BUILD=|STOCK_SEPOLICY|boot.img" "$log" | tail -n 20
for zip in out/target/product/a23/*.zip; do
    [[ -f "$zip" ]] || continue
    echo "A23_ZIP=$work/$zip ($(du -h "$zip" | cut -f1))"
done
echo "A23_COLAB=OK elapsed=$(elapsed)"
