#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run this only from the root of an already-synced Evolution X source tree.

# Android's envsetup intentionally runs probe commands that may return a
# non-zero status, so global errexit/nounset are not compatible with it.
set -o pipefail

if [[ ! -f build/envsetup.sh ]]; then
    echo "error: run this script from the Evolution X source root" >&2
    exit 1
fi

source build/envsetup.sh
export EVO_BUILD_TYPE=Unofficial
export WITH_GMS=false
lunch lineage_a23-cp2a-userdebug || exit 1

# Keep the first server build single-purpose. Do not install packages, mutate
# the manifest, change global Git settings, or upload artifacts from here.
# The first bring-up server has 49 GiB RAM (+ swap). Limit parallelism to
# avoid an OOM during Soong/Kati while keeping the 19 vCPUs reasonably busy.
m -j12 evolution
