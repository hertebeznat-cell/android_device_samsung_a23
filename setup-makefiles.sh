#!/bin/bash
#
# Copyright (C) 2024-2026 The Evolution X Project
# SPDX-License-Identifier: Apache-2.0
#
# Generate vendor makefiles from proprietary-files.txt

set -e

DEVICE=a23
VENDOR=samsung

MY_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "$MY_DIR" ]]; then MY_DIR="$PWD"; fi

ANDROID_ROOT="$MY_DIR/../../.."
HELPER="${ANDROID_ROOT}/tools/extract-utils/extract_utils.sh"

if [ ! -f "$HELPER" ]; then
    echo "Unable to find helper script at $HELPER"
    exit 1
fi

source "$HELPER"

# Initialize the helper for our device
setup_vendor "$DEVICE" "$VENDOR" "$ANDROID_ROOT" false false false

# Generate vendor makefiles
write_makefiles "$MY_DIR/proprietary-files.txt" true

# Finish
write_footers
