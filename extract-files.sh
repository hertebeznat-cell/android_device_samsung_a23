#!/bin/bash
#
# Copyright (C) 2024-2026 The Evolution X Project
# SPDX-License-Identifier: Apache-2.0
#
# Extract proprietary files from a running Samsung Galaxy A23 device

set -e

DEVICE=a23
VENDOR=samsung

# Default path for vendor tree
VENDOR_PATH="vendor/${VENDOR}/a235f"

MY_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "$MY_DIR" ]]; then MY_DIR="$PWD"; fi

ANDROID_ROOT="$MY_DIR/../../.."
HELPER="${ANDROID_ROOT}/tools/extract-utils/extract_utils.sh"

if [ ! -f "$HELPER" ]; then
    echo "Unable to find helper script at $HELPER"
    exit 1
fi

source "$HELPER"

# Default to extracting from connected device via adb
SRC="adb"

while [ "$1" ]; do
    case "$1" in
        -s|--src)
            SRC="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [ -z "$SRC" ]; then
    SRC="adb"
fi

# Initialize the helper for our device
setup_vendor "$DEVICE" "$VENDOR" "$ANDROID_ROOT" false false false

extract "$MY_DIR/proprietary-files.txt" "$SRC" "$VENDOR_PATH"

"$MY_DIR/setup-makefiles.sh"
