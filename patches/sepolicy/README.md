# API 30 stock vendor policy on Evolution X cnb

The SEZB1 vendor policy targets SELinux API 30.0. Evolution X cnb removed
the corresponding compatibility modules and their source CIL files.
The patch restores the original API 30 mapping chain on top of API 31,
without replacing current platform policy or disabling neverallow checks.

Reviewed target: `Evolution-X/system_sepolicy` at
`c3997bf608b40a7217d0eb2257af887afa78617b`.
The restored module definitions and three compatibility CIL inputs come from
`LineageOS/android_system_sepolicy` at
`885cc500f6078a766d1f6def5ce4c06c55841773`.
The helper records and checks the original CIL Git blob identities.

From the workspace root, without downloading or building anything:

```text
python -B device/samsung/a23/tools/test_sepolicy_patch.py
```

With an existing platform checkout, pass `--source system/sepolicy` to verify
the reviewed patch context before or after application. The guarded server
entrypoint applies the patch before preflight and policy compilation.

The device product explicitly installs the five runtime mapping/compatibility
modules, and the stock policy compatibility target links the same inputs.

## Single owner for stock vendor inputs

Apply `0002-select-stock-vendor-policy-owner.patch` after `0001`. Enable its
device-only mode with `$(call soong_config_set_bool,a23,use_stock_vendor_policy,true)`.
The typed boolean is required by the Blueprint selectors. `sources.json` records the exact upstream Git blobs
and patch checksums. The upstream files were inspected through the connector
in memory; no platform source checkout was downloaded or saved on the PC.

The standard module names install the stock `plat_pub_versioned.cil`,
`vendor_sepolicy.cil`, and `plat_sepolicy_vers.txt`. Source generators retain
separate, non-installable names for the default mode. Context and MAC modules
select raw stock inputs through filegroups, preserving their normal compiler,
sorting, `checkfc`, `checkseapp`, and platform seapp neverallow checks. Vendor
denial metadata also uses its existing `vendor_bug_map` module.

The combined policy is freshly compiled from current platform policy, actual
stock vendor CIL, and the API 30 mapping/compatibility inputs. Its platform,
system_ext and product hashes use those same legacy mappings. Stock mode
disables the absent ODM CIL module and removes its required dependency.
Recovery retains `target_recovery` permissions while selecting the same stock
vendor inputs and API 30 compatibility files. It never reuses the main binary
as its recovery policy.

The compatibility test factory adds an explicit API 30 test using the actual
stock CIL and enabled neverallow checks. Existing upstream compatibility tests
and `sepolicy_neverallows` remain in place. The API 30 test deliberately does
not depend on an unavailable `30.0_plat_pub_versioned.cil` API snapshot.

Integration must remove direct copy rules for the eleven selected vendor
files and all four stock ODM precompiled policy/hash files. The vendor tree
exports their raw inputs with visibility to `//system/sepolicy:__subpackages__`.
The current platform `BOARD_SEPOLICY_VERS` stays unchanged; the installed stock
version file describes vendor API 30, and only the selected mapping inputs
switch to API 30. Do not alias the current `plat_mapping_file` generator.

Generated CIL/mapping references use `device_common_srcs`; raw filegroups keep
ordinary `srcs`. The three policy/version installer wrappers explicitly use
`compile_multilib: "common"` to preserve the original modules' common variant.

Without the stock-mode flag, selectors retain the original source inputs.
The patch was checked against all four exact upstream files in memory. These
source checks do not prove that Samsung private symbols, current neverallows,
or hardware behavior are compatible. Actual `selinux_policy`, API 30 and
recovery policy compilation remain mandatory on the authorized build server.
