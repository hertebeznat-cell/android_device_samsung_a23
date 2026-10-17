#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The reviewed vendor tree is not reproducible with legacy extract-utils.
# Fail before contacting adb or overwriting either vendor directory.
echo "Legacy extraction is disabled: it generated vendor/samsung/a23 instead of a235f and discarded stock VNDK/FCM requirements." >&2
echo "Stage stock firmware separately, preserve the SEZB1 VINTF baseline and review per-file changes before updating vendor/samsung/a235f." >&2
echo "See BRINGUP_AUDIT.md and tools/android-image/audit_vendor_refresh.py in the workspace." >&2
exit 2
