#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from an already synced, dedicated Evolution X 11.10 tree on Linux.
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
device=device/samsung/a23
python3 "$device/tools/preflight.py" --root "$PWD" --server
mkdir -p a23-logs
stamp=$(date -u +%Y%m%dT%H%M%SZ)
repo manifest -r -o "a23-logs/manifest-$stamp.xml"
export EVO_BUILD_TYPE=Unofficial WITH_GMS=true
set +u
source build/envsetup.sh
lunch lineage_a23-bp4a-userdebug
# pipefail retains the compiler's exit status when tee succeeds.
m -j"${BUILD_JOBS:-12}" evolution 2>&1 | tee "a23-logs/build-$stamp.log"
find out/target/product/a23 -maxdepth 1 -type f \
    \( -name '*.zip' -o -name 'boot.img' -o -name 'recovery.img' -o -name 'dtbo.img' -o -name 'vbmeta.img' \) \
    -exec sha256sum {} + | tee "a23-logs/SHA256SUMS-$stamp"
echo "Build completed. Images still require device boot and hardware testing."
