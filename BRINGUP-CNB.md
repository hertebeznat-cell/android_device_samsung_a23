# SM-A235F: Evolution X 12.3 / Android 17 bring-up

Reviewed 2026-10-17. **No Android 17 compilation or boot test has completed.**
The user selected Android 17 and now authorizes public GitHub publication of
the required device/vendor changes. Platform/kernel source downloads and
compilation remain restricted to Crave, with no Devspace or clean option.
Job [306056](https://foss.crave.io/app/#/build/info/306056?team=14) failed while
waiting for its local archive, before source sync or compilation. That private
archive/uploader path is retired; the replacement reads public GitHub sources.

## Selected platform

- Evolution X `cnb`, Android 17, lunch `lineage_a23-cp2a-userdebug`.
- `vendor_evolution/config/version.mk`: `EVO_VERSION_BASE := 12.3`.
- Unofficial with Google apps. No bundled root or insecure ADB.
- Manifest reviewed at `bc6d0f9172fec886ef2a60d559a2516fd24499ef`;
  vendor_evolution at `4963fb0c4d9c0827511a35f04e84011d83c7a075`.
- Kernel source/config and SEZB1 blob/DTB baseline are unchanged. Existing six
  kernel fixes remain required. Do not mix stock 4.19.157 modules with this
  source-built 4.19.325 kernel.

`source-lock.json` records reviewed references and patch provenance. It is not
a full lock of every platform repository. The server entrypoint saves the
resolved manifest and applied changes for each build.

## Public-source Crave entrypoint

Publish the reviewed device and vendor trees to their public
`codex/cnb-a23-bringup` branches and record each full 40-character commit SHA.
All integration patches, checks and build entrypoints are inside the device
repository; the vendor repository contains its corresponding reviewed inputs.
No source files need to be transferred from the PC during a build.

Inside one ordinary queued `crave run`, fetch the device entrypoint from its
immutable public commit into `/tmp`, then supply both published commit pins:

```bash
set -e
test -f .repo/manifest.xml
device_revision=REPLACE_WITH_PUBLISHED_DEVICE_COMMIT_SHA
vendor_revision=REPLACE_WITH_PUBLISHED_VENDOR_COMMIT_SHA
entrypoint=$(mktemp /tmp/a23-crave-cnb.XXXXXX.sh)
curl -fL --retry 3 \
    "https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/$device_revision/crave_build.sh" \
    -o "$entrypoint"
A23_REMOTE_BUILD=1 A23_DEVICE_REVISION="$device_revision" \
    A23_VENDOR_REVISION="$vendor_revision" BUILD_JOBS=12 bash "$entrypoint"
```

The Crave command uses `--no-patch --no-artifacts`; it must run from the
project's existing Android root. The entrypoint initializes Evolution X `cnb`
with `--depth=1`, writes its own root `.repo/local_manifests/a23.xml`, and uses
`/opt/crave/resync.sh`. Its device/vendor projects select the published commits,
then verify both checked-out HEADs before applying the integration patches.
Downloading the entrypoint to `/tmp` keeps synchronization from replacing the
script while it runs. Neither private repositories nor a local archive,
uploader, nested source checkout or `--clean` is part of this flow.

## Corrections in this review

1. Aligned product lunches, scripts, version expectations and server manifests
   on cnb/cp2a. Retained the exact kernel and added the missing VNDK 30 snapshot
   to both manifest entrypoints. Removed automatic dependencies that could
   silently select an unrelated kernel.
2. Unified the build entrypoints: integration patches precede server preflight;
   envsetup/lunch failures stop the pipeline. Every entrypoint requires explicit
   Linux-server opt-in and rejects WSL. GMS/Unofficial selection is consistent.
3. Fixed five stock ODM NFC SKU manifest modules installing into vendor instead
   of ODM. Removed the duplicate NXP NFC service declaration while retaining its
   HIDL interfaces and Samsung/NXP selection triggers.
4. Removed a competing source health service; retained the installed Samsung
   HIDL 2.1 service, supported by the framework. Exported the Qualcomm display
   Soong namespace needed by selected source libraries. Restored the Qualcomm
   legacy-um policy include because selected device contexts reference its
   firmware and camera types. Aligned wide-color/color-management properties
   with the actual SEZB1 display capability declarations.
5. Moved Wi-Fi resources to ServiceWifiResources and removed four framework
   overlay entries whose resources no longer exist on cnb.
6. Restored API 30 SELinux compatibility modules and original mapping inputs as
   a targeted integration patch. They extend the supported API 31 mapping chain;
   the product installs the legacy maps. A second integration patch now selects
   the actual stock vendor CIL and context inputs through standard platform
   modules. Eleven vendor outputs have one installer each; fifteen competing
   raw-copy rules, including the old ODM binary and its three hashes, are gone.
   Main and recovery policy are rebuilt against their current Android 17
   platform variants and the same vendor API 30 inputs. Context/MAC processing,
   checkseapp, neverallow and upstream policy tests remain enabled.
   The selector uses a typed Soong boolean, and CIL inputs/wrappers use the
   common device variants required by the current Soong module definitions.
7. Kept the stock vendor FCM 5, VNDK 30 and System SDK 30 declarations. Raising
   declared versions would conceal compatibility requirements. The legacy FCM
   integration restores checks required by this stock vendor.
8. Connected the existing non-A/B packaging fix to the shared pipeline. Info-ZIP
   now preserves symlinks when packaging extracted target-files, preventing a
   ROOT/d link from traversing the build host's debugfs.
9. Disabled the obsolete extraction/regeneration entrypoints, which targeted
   the wrong vendor directory and changed VINTF declarations automatically.
   The audited SEZB1 vendor tree must be preserved until extraction is migrated.
10. Added source/install audits and workflow regressions. Patched fixture tests
    no longer let a parent Git worktree silently skip patch paths. OTA selection
    requires a fresh A23 OTA with Android metadata; random or old ZIPs do not
    count as success. Checksums and build logs stay on the server.
11. Removed the competing raw ODM `build.prop` installer. Its single OEM feature,
    `ro.vendor.qti.va_odm.support=1`, is retained in `odm.prop` through
    `TARGET_ODM_PROP`; the platform generator owns ODM build identity and CPU
    properties. This matches the current [ODM property target](https://github.com/Evolution-X/build/blob/646e5671fe2617107d12ec56b1ef11ad12bc087f/core/sysprop.mk)
    and [Soong build property module](https://github.com/Evolution-X/build_soong/blob/1ac47f839dbb998440f558d886ba03a61954cfe8/Android.bp).

## Local verification

The local preflight and vendor source/install audit check file existence,
XML syntax, selected modules, duplicate copy destinations/services, partition
placement, filesystem identities and integration configuration.

All six kernel patches apply and reverse-check on 20 exact files from the
already available pinned repository; original regressions are detected before
application and absent afterward. No compiler was run.

The Android 17 r1 VNDK `apex/Android.bp` has Git blob
`baf8d19ec088a6aaa456ac43e4aefba9c3dc6580`, identical to the existing offline
Android 16 fixture. Its signing inputs also match the reviewed Android 17
files. This permits offline patch validation without downloading another
source tree. It does not test the VNDK runtime linker.

The vendor ELF inventory contains both ARM and AArch64 userspace binaries and
Hexagon firmware. Vendor/Samsung SONAME dependencies present in this inventory
are available for their respective architecture; external platform/VNDK
dependencies and symbol versions still require the generated platform images.

Workflow/OTA regression tests pass, and the existing official
filesystem generator reproduces all 33 stock OEM accounts and 15 permission
rules. SELinux API 30 and FCM 5/R4.19 restoration provenance checks pass. The
VINTF fixture test also checks idempotency, reverse application and refusal to
overwrite server edits. These are source checks, not a compiled policy or ROM.

The artifact checksum path works on Python 3.10 without `hashlib.file_digest`.
The server log directory retains the complete integration patch set and source
lock, including new CIL/FCM files that a plain `git diff` would omit.

The SELinux ownership audit passes, with thirteen regressions covering restored
copy collisions, wrong selectors/exports, changed patch data, obsolete ODM
binaries, stale policy digests, changed contexts and merged system_ext output.
The new patch's 27 hunks match four exact upstream files in memory; their Git
blob identities are recorded in `patches/sepolicy/sources.json`. No platform
source files were downloaded to the PC. The server must compile both main and
recovery policy, then inspect staged CIL, contexts, MAC permissions and all
three actual API 30 policy digests before proceeding to the kernel.

The vendor seapp coredomain check was also traced through the current
[product configuration](https://github.com/Evolution-X/build/blob/646e5671fe2617107d12ec56b1ef11ad12bc087f/core/product_config.mk#L659).
It is automatically required above vendor API 34; this device keeps its actual
shipping API 31. No explicit override was found in the reviewed device/vendor
configuration or Evolution common product configuration, and no check-disable
flag was added. The resolved server configuration and normal checkseapp
compilation remain authoritative.

```text
python -B device/samsung/a23/tools/check_selinux_ownership.py --root .
python -B -m unittest discover -s device/samsung/a23/tools -p test_selinux_ownership.py
```

## What remains to prove on Crave

- Full Soong/Make build with the selected cnb dependencies and compiler.
- Actual Samsung vendor CIL against current platform policy and legacy maps.
  The installation-ownership conflict is resolved in the source configuration;
  compilation against current private symbols and neverallows is still
  unverified. Both main and recovery compilation and staged-output validation
  must run before building the kernel/ROM.
- Full `checkvintf` with restored FCM 5/kernel requirements; original HAL versions
  must also be implemented by Android 17. XML parsing alone is insufficient.
- VNDK 30 APEX, linker namespaces, ELF symbols and source/blob output ownership.
  Existing broad BUILD_BROKEN settings are still technical debt; they are not
  evidence of a correct installed image.
- Resolved kernel `.config`, DTB/DTBO/kernel ABI, boot header and image sizes.
- Fresh non-A/B OTA contents and fit inside the real dynamic-partition budget.
- Physical boot, encryption and every hardware function, with crash logs.

Do not describe the trees as fully fixed or flash-ready before these checks.
Job 306056 provides no policy, kernel, ROM or boot validation. Public source
publication and a replacement ordinary Crave job are separate from these
local source checks. No platform/kernel source sync or compilation ran on the
PC, and no phone action was performed.

## Documentation and source authority

Reviewed the official build environment, lunch, build flags, installation,
bug reporting, support-new-device, maintainership, onboarding, automatic
building and code-of-conduct pages. Their build examples still mix `bq2`,
`bp4a`, Android 14 requirements and official-maintainer instructions.
The live cnb manifest and version source determine this unofficial target.

- https://wiki.evolution-x.org/setting-up-env
- https://wiki.evolution-x.org/en/lunch
- https://wiki.evolution-x.org/en/build_flags
- https://wiki.evolution-x.org/installing-evolution-x
- https://wiki.evolution-x.org/reporting-a-bug
- https://wiki.evolution-x.org/en/support-new-device
- https://wiki.evolution-x.org/apply-for-maintainership
- https://wiki.evolution-x.org/en/onboarding
- https://wiki.evolution-x.org/en/automatic-building
- https://wiki.evolution-x.org/code-of-conduct
- https://github.com/Evolution-X/manifest/tree/cnb
- https://github.com/Evolution-X/vendor_evolution/blob/cnb/config/version.mk

Unofficial builds do not use Evolution's official maintainer CI credentials
or private keys. For later distribution, generate and back up your own stable
signing keys on the authorized server using the unofficial signing template.
Keys were not generated or fetched here; signing does not prove device boot
or guarantee Play Integrity results.
