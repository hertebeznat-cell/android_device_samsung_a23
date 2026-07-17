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

# Android 16 no longer publishes the legacy VNDK/system SDK declarations that
# shipped in Samsung's Android 12 device compatibility matrix.
sed -i \
    -e '/<vendor-ndk>/,/<\/vendor-ndk>/d' \
    -e '/<system-sdk>/,/<\/system-sdk>/d' \
    "$VENDOR_PATH/proprietary/vendor/etc/vintf/compatibility_matrix.xml"
sed -i \
    -e 's/target-level="5"/target-level="6"/g' \
    "$VENDOR_PATH/proprietary/vendor/etc/vintf/manifest.xml"

# Android 16's host_init_verifier rejects Samsung extension interfaces when
# their proprietary .hal definitions are unavailable. The standard Android
# interfaces above them still start the same supplicant and hostapd services.
sed -i '/interface vendor\.samsung\.hardware\.wifi\.supplicant@3\.[01]::ISehSupplicant default/d' \
    "$VENDOR_PATH/proprietary/vendor/etc/init/android.hardware.wifi.supplicant-service.rc"
sed -i '/interface vendor\.samsung\.hardware\.wifi\.hostapd@3\.0::ISehHostapd default/d' \
    "$VENDOR_PATH/proprietary/vendor/etc/init/hostapd.android.rc"
sed -i '/interface vendor\.samsung\.hardware\.nfc@2\.0::ISehNfc default/d' \
    "$VENDOR_PATH/proprietary/vendor/etc/init/nxp.android.hardware.nfc@1.2-service.rc"
sed -i \
    -e '/interface vendor\.qti\.hardware\.wifi\.wifilearner@1\.0::IWifiStats wifiStats/d' \
    -e '/^[[:space:]]*disabled[[:space:]]*$/d' \
    "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.qti.hardware.wifi.wifilearner@1.0-service.rc"
sed -i \
    -e '/interface vendor\.samsung\.hardware\.authfw@1\.0::ISehAuthenticationFramework default/d' \
    "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.authfw@1.0-service.rc"

# Keep closed Samsung/Qualcomm HIDL blobs, but drop init interface declarations
# that cannot be verified without their unavailable proprietary .hal sources.
strip_interface() {
    local file="$1"
    local declaration="$2"
    local tmp
    tmp="$(mktemp)"
    grep -Fv "interface $declaration" "$file" > "$tmp"
    cat "$tmp" > "$file"
    rm -f "$tmp"
}

strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.tlc.ucm@2.0-service.rc" \
    'vendor.samsung.hardware.tlc.ucm@2.0::ISehUcm default'
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.tlc.payment@1.0-service.rc" \
    'vendor.samsung.hardware.tlc.payment@1.0::ISehTlcPayment default'
for version in 2.0 2.1 2.2 2.3; do
    strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.wifi@2.0-service.rc" \
        "vendor.samsung.hardware.wifi@${version}::ISehWifi default"
done
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.camera.provider@4.0-service_64.rc" \
    'vendor.samsung.hardware.camera.provider@4.0::ISehCameraProvider legacy/0'
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.security.skpm@1.0-service.rc" \
    'vendor.samsung.hardware.security.skpm@1.0::ISehSkpm default'
for version in 1.0 1.1; do
    strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.tlc.kg@1.1-service.rc" \
        "vendor.samsung.hardware.tlc.kg@${version}::ISehKg default"
    strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.tlc.hdm@1.1-service.rc" \
        "vendor.samsung.hardware.tlc.hdm@${version}::ISehHdm default"
done
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/wsm-service.rc" \
    'vendor.samsung.hardware.security.wsm@1.0::ISehWsm default'
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.tlc.mpos_tui@1.0-service.rc" \
    'vendor.samsung.hardware.tlc.mpos_tui@1.0::ISehMposTui default'
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.tlc.iccc@1.0-service.rc" \
    'vendor.samsung.hardware.tlc.iccc@1.0::ISehIccc default'
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.hqm@1.0-service.rc" \
    'vendor.samsung.hardware.hqm@1.0::ISehHqm default'
strip_interface "$VENDOR_PATH/proprietary/vendor/etc/init/vendor.samsung.hardware.security.drk@2.0-service.rc" \
    'vendor.samsung.hardware.security.drk@2.0::ISehDrk default'

"$MY_DIR/setup-makefiles.sh"
