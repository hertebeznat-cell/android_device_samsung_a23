# A23 build 299343 audit — 2026-09-12

Status: **not boot-validated; not all bring-up issues are resolved**.

## Confirmed build failure and fixes

The log ran `/tmp/a23-crave-9cd33cf.sh`. It contains two compiler errors:

- `drivers/adsp_factory/ssc_core.c:899`: `print_ssr_history()` lacks an explicit
  `void` prototype. Patch 0003 fixes the declaration without disabling warnings.
- `mm/vmscan.c:5694`: a partially integrated vmpressure backport calls the
  six-argument interface with five arguments. Patch 0004 passes `sc->order`.
  The same backport left two subtree-accounting calls per reclaim pass; the
  patch removes the later duplicate, keeping accounting before slab pages are
  added to the reclaimed counter.

The prior ARM64/ARM32 target flags are present in the actual compiler command.
The prior sched_param and OpenSSL host-tool errors did not recur in this log.

## Reproducible checks (no local kernel compilation)

Run from the Android workspace root:

```text
python -B device/samsung/a23/tools/test_kernel_patches.py upstream/solstice-sm6225
python -B device/samsung/a23/tools/preflight.py --root .
bash -n device/samsung/a23/crave_build.sh
```

The patch test reads 14 exact source blobs from kernel revision
`8c34b1fc1e921fcac33e839f7d6e9f3ea732221b` into a disposable directory.
It detects the original prototype, argument-count and duplicate-accounting
regressions, applies all four patches, checks reversibility, and reruns the
source audit. It does not modify the existing kernel checkout or run a compiler.

The remote script now checks device/vendor commit IDs, audits patched sources,
runs `kernelconfig`, checks the **resolved** `.config`, builds `kernel`, then
builds `evolution`. These stages share one job/output tree; no clean, Devspace,
new queue entry or manual cache/platform deletion is introduced.

## Remaining findings — do not label this ROM ready to flash

### Build 299918 correction

The build stopped before compilation because android-16.0.0_r4 defines VNDK
APEX 31-34 only. Earlier inspection of main was not evidence for this tag.
Patch patches/vndk/0001-restore-vndk30-apex.patch adds version 30 with the same
platform defaults, signing inputs and system_ext placement. The entrypoint
applies it before preflight. tools/test_vndk_patch.py verifies the patch against
the exact tag commit f2caada6c9378ba37879c5b952fab07cf0f46e16, including signing
input existence and unique modules 30-34. This fixes the observed missing-module
setup error; it does not establish runtime ABI or SELinux compatibility.

### Validation workflow

The local remote-entrypoint changes now build `selinux_policy`, the stock
vendor policy compatibility target, and `com.android.vndk.v30` before the
kernel and userspace, as stages of a normal complete ROM build. There is no
validation-only mode. Passing generated policy tests does not prove that
copied stock policy or mixed legacy/current ELF dependencies work at runtime.
The stock policy ownership conflict is still unresolved; do not call this a
completed SELinux migration.

### Build 299833 follow-up

The supplied log contains three new compiler diagnostics: TFA9878 reference
temperature enum conversion and missing void prototypes in ST timestamp and
Novatek LCD power checking. Patch 0006 retains the temperature function's own
enum type in a separate local result and adds explicit prototypes. It does not
suppress diagnostics. The six-patch test covers 20 exact pinned source files,
detects all three regressions before patching and checks the corrected sources.
Full compilation, VNDK and SELinux compatibility are still not established.

### Build 299628 follow-up — 2026-09-14

The supplied log stops during kernel compilation. Its four compiler errors are
TAS256x cleanup indentation, an implicit-int camera close callback, and two ST
touchscreen definitions lacking void prototypes. Patch 0005 fixes all four
without relaxing compiler diagnostics or changing cleanup control flow. The
touchscreen header already declares both functions with void parameters.
The exact pinned-source test now covers 17 files and all five patches, detects
these regressions before application, and passes after application. This is a
source regression test, not local compilation or proof of complete buildability.
No new Crave job was submitted for this follow-up.

### Follow-up fixes on 2026-09-12

- Migrated all 33 stock OEM identities into `config.fs`. The official Android 16
  `fs_config_generator.py` produces vendor passwd/group identical to SEZB1;
  ODM account tables remain empty, as in stock.
- Migrated 15 canonical `vendor/` permission/capability rules from the stock
  binary fs-config table. The official generator round-trip preserves each
  path, mode, UID, GID and capability mask. Legacy `system/vendor/` aliases are
  not installed in the dedicated vendor partition. Removed two invented HAL
  permission entries targeting nonexistent fingerprint/sensors executables.
- Removed eight copy rules for passwd/group/fs_config_files/fs_config_dirs
  across vendor and ODM. These outputs now have the generated owner; stock
  reference files remain in the repository for regression checks.
- Restored the stock VINTF device/kernel FCM level 5 and vendor requirements for
  VNDK/System SDK 30. Both base VINTF files now match the extracted SEZB1 files
  (ignoring line endings). Raising FCM to 6 and deleting version requirements
  was not an ABI migration. Added baseline checks and disabled the obsolete
  `tools/android-image/apply_vendor_fixups.ps1` entrypoint that made those edits.

Account/filesystem regression command (official AOSP sources downloaded to
the workspace `artifacts` directory):

```text
python -B device/samsung/a23/tools/test_fs_config.py --generator artifacts/aosp16_fs_config_generator.py --aid-header artifacts/aosp16_android_filesystem_config.h --capability-header artifacts/aosp16_capability.h
```

References: [AOSP OEM AIDs and filesystem configuration](https://source.android.com/docs/core/permissions/filesystem),
[AOSP FCM lifecycle](https://source.android.com/docs/core/architecture/vintf/fcm).

### Still unresolved

1. The log reports **472 distinct installation paths with overriding rules**.
   These include stock copied HALs/libraries versus source-built modules and
   generated vendor/odm metadata. They are not 472 compiler failures, but output
   ownership must be decided per path before claiming image correctness. These
   warnings can include rules for modules not selected for the final product:
   they are not proof that both producers are installed. Eight metadata copy
   rules were removed locally. Two unused base VINTF prebuilt modules were also
   removed: BoardConfig already supplies these XMLs to assemble_vintf. The XML
   inputs and individual HAL fragments are preserved. Preflight prevents these
   base prebuilt/raw-copy installers from being reintroduced. Remaining paths
   need review against the selected dependency graph and installed-file lists,
   not blanket deletion based on this historical log. This is not a fresh build.
2. Stock `vendor/etc/selinux/plat_sepolicy_vers.txt` is **30.0**. Stock vendor CIL,
   contexts and ODM precompiled policy collide with generated policy files.
   Current device policy is only a small set of type declarations. Removing
   stock policy or replacing it blindly is not a verified SELinux port.
3. The vendor requires VNDK 30 (`vendor/default.prop` and the restored matrix),
   while BoardConfig selects `current`. The reviewed Evolution `bka/default.xml`
   has VNDK snapshots 31–34, not 30. The local device changes now request the
   official VNDK 30 snapshot at 5f9884aa352825291757dfd6694b874ad8c1805e and
   PRODUCT_EXTRA_VNDK_VERSIONS += 30. Server preflight checks the exact snapshot
   and that the platform defines com.android.vndk.v30. This has not yet been
   synced or compiled on a server. Linker namespace selection and mixed
   current/legacy blob ABI compatibility still need validation; changing
   the reported VNDK number alone cannot supply missing symbols/libraries.
4. Legacy VNDK 30 ELF dependencies, full VINTF/kernel compatibility, image sizes,
   kernel/DTB ABI and actual boot remain unverified. Static checks cannot prove
   these; full build validation and device logs are required.

No remote job was created, canceled or restarted during this audit. Changes are
local until publication is explicitly reported. No promise of a successful
next full build or successful device boot is made.
