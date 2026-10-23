#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Compile the platform policy together with the untouched SEZB1 vendor policy,
# using the same inputs and secilc flags as init's boot-time compilation
# (system/core/init/selinux.cpp). A failure here means a boot loop on device.
#
set -euo pipefail

: "${OUT:?run lunch first}"
: "${ANDROID_HOST_OUT:?run lunch first}"
stock=vendor/samsung/a235f/reference/selinux
# init reads the vendor policy version from plat_sepolicy_vers.txt; Samsung's
# vendor_sepolicy_version holds SEPF metadata instead.
version=$(cat "$stock/plat_sepolicy_vers.txt")
version=${version%%[[:space:]]*}

system="$OUT/system/etc/selinux"
system_ext="$OUT/system/system_ext/etc/selinux"
product="$OUT/product/etc/selinux"
for file in "$system/plat_sepolicy.cil" "$system/mapping/$version.cil"; do
    [[ -f "$file" ]] || { echo "missing $file" >&2; exit 1; }
done

# Optional inputs are added exactly when init would find them on device.
# -v as init uses it: secilc then names the rule behind any failure.
arguments=("$system/plat_sepolicy.cil" -m -M true -G -N -v -c 31
           "$system/mapping/$version.cil")
optional() { [[ -f "$1" ]] && arguments+=("$1"); return 0; }
optional "$system/mapping/$version.compat.cil"
if [[ -f "$system_ext/system_ext_sepolicy.cil" ]]; then
    arguments+=("$system_ext/system_ext_sepolicy.cil")
    optional "$system_ext/mapping/$version.cil"
    optional "$system_ext/mapping/$version.compat.cil"
fi
if [[ -f "$product/product_sepolicy.cil" ]]; then
    arguments+=("$product/product_sepolicy.cil")
    optional "$product/mapping/$version.cil"
fi
arguments+=("$stock/plat_pub_versioned.cil" "$stock/vendor_sepolicy.cil")

output=$(mktemp)
trap 'rm -f "$output"' EXIT
"$ANDROID_HOST_OUT/bin/secilc" "${arguments[@]}" -o "$output" -f /dev/null
echo "STOCK_SEPOLICY=OK vendor=$version ($(stat -c %s "$output") bytes)"
