#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Generic generation loses the reviewed VINTF/fs-config/symlink ownership.
echo "Legacy vendor regeneration is disabled: the a235f makefiles contain reviewed installation rules that proprietary-files.txt does not reproduce." >&2
echo "Preserve vendor/samsung/a235f and review changes against BRINGUP_AUDIT.md; do not run generic setup_vendor for a23." >&2
exit 2
