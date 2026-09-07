# Galaxy A23 SM-A235F — Evolution X 11.10 preparation

Reviewed 2026-09-07. **Prepared for a server bring-up build, not boot-tested.**
No Android or kernel compilation was performed on the Windows PC.

## Source selection

- Evolution X `bka`, Android 16 QPR2, `lineage_a23-bp4a-userdebug`.
- `vendor_evolution/config/version.mk` reports `EVO_VERSION_BASE := 11.10`.
- `cnb` is Android 17 and must not be used for this build.
- Source kernel: blxyzY/android_kernel_samsung_sm6225 at
  `8c34b1fc1e921fcac33e839f7d6e9f3ea732221b`, Linux 4.19.325.
- Kernel base: `a23_eur_open_defconfig`, followed by the external AOSP fragment
  in `configs/kernel/a23_aosp.config`, merged by Evolution's kernel build rules.
- Kernel and platform commits reviewed are recorded in `source-lock.json`.
  A branch manifest is not a full reproducibility lock; `server_build.sh` saves
  the resolved `repo manifest -r` for the actual build.

## What the kernel repository establishes

It is real source code containing A23 configs, Samsung/QCOM drivers, a kernel
Makefile, SELinux, BinderFS, PSI, BPF and inline-encryption support. Its main
defconfig identifies itself as SolsticeKernel and builds WLAN into the kernel.
The checked Makefile has LLVM/binutils and integrated assembler support.
Its sample build script still references a local Samsung Clang 10/GCC toolchain;
the expanded defconfig records Clang 11. Neither proves a modern compiler build.

No release asset or build provenance tying this exact commit to the user's
working Android 16 / One UI 8 image was found. It must be treated as a candidate,
not a verified replacement boot image. Kernel version alone does not establish
Android userspace compatibility. The AOSP fragment enables missing cgroup-pids
and securityfs, preserves PSI/Binder/BPF, and disables Samsung UH/RKP/KDP/DEFEX
configuration instead of disabling SELinux. Some Samsung config symbols may
already have been removed by upstream; inspect the generated .config on Linux.

## Corrected integration defects

- Replaced the selected stock prebuilt kernel with pinned source compilation.
- Changed `cnb/cp2a` to `bka/bp4a`; added a 11.10 version check.
- Added the missing `hardware/samsung` manifest dependency.
- Removed duplicate fstab producers (vendor copy and Make module). Boot header
  v2 uses its boot ramdisk; no nonexistent vendor_boot ramdisk is populated.
- Kept one ext4 dynamic-partition fstab. Corrected UFS identification and
  Qualcomm firmware mounts: APNHLOS -> firmware_mnt, modem -> firmware-modem.
- Removed eMMC-specific/wrapped-key assumptions from userdata encryption.
  A clean data format is required when changing this encryption configuration;
  do not test by expecting an old encrypted userdata image to remain readable.
- Removed copied stock .ko files and module indices. WLAN is built-in with the
  new kernel; the old stock WLAN insmod was removed. Do not mix 4.19.157 modules
  with 4.19.325; any subsequently needed modules must come from the same build.
- Removed duplicate fingerprint/DSP/thermal service declarations.
- Selected the actual stock HAL manifest/matrix as build inputs, and removed
  competing base VINTF copy modules and conflicting source HAL services.
  The old synthetic `manifest.xml` is retained for reference but is not selected.
- Removed 45 duplicate copy destinations, preserving the stock HAL's audio,
  GPS, media and Wi-Fi configuration rather than depending on copy ordering.
- Removed 22 redundant explicit source-package entries already supplied as
  stock blobs; removed unverified CFQ/GPU tuning and the extra target init module.
- Re-enabled kernel OTA VINTF enforcement; no success-by-skipping-kernel-check.

## Firmware provenance and remaining validation

### Additional installation audit

- Recreated 77 stock library/firmware/RFS symlinks with Soong `install_symlink`.
  The mappings are versioned in `vendor-links/links.json`; plain target-text
  files from Windows extraction must not be copied as if they were symlinks.
- Selected Android's source `toybox_vendor` with its generated applet links,
  removing the competing stock binary copy. The platform owns `vendor/odm`.
- Installed the full stock ueventd rules at `/vendor/etc/ueventd.rc`, which
  Android 16's `/system/etc/ueventd.rc` imports. The previous synthetic file at
  `/vendor/ueventd.a23.rc` was not automatically loaded and is no longer selected.
- Preflight now checks symlink copy collisions, relative library targets,
  toybox ownership, and the canonical ueventd destination.

These fixes address confirmed image-installation omissions, not a proven cause
of the observed 12-second reboot. Reference implementations reviewed:
`android_build_soong/lineage-23.2/etc/install_symlink.go`, AOSP Android 16 r4
`external/toybox/Android.bp`, `system/core/init/ueventd.cpp`, and
`system/core/rootdir/ueventd.rc`.

The vendor/odm blobs were refreshed from the user's full **A235FXXSEEZB1** stock
archive on 2026-09-07. Vendor patch is **2026-02-05**. Of 2323 tracked blob files,
2224 already matched, 75 were updated with SHA-256 verification, and 24 reviewed
AOSP adaptations or uninstalled stock artifacts were retained. No tracked blob
was missing from the stock extraction. Old overwritten files are backed up under
`stock_firmware/SEZB1-full/before-refresh`; the extraction and refresh JSON reports
record provenance. The pristine extraction remains separate from the vendor tree.

Boot and DTBO compressed hashes match the previously saved SEZB1 files. The
old mixed EYG1/SEZB1 baseline has therefore been removed for installed blobs, but
the source-built kernel's compatibility is still untested. Stock kernel modules
and recovery-restoration artifacts retained for reference are not installed.
The stock recovery restoration script and init service were removed from the
product copy list; they must not overwrite a custom recovery.

SEZB1 still declares vendor API/VNDK 30, stock FCM/kernel target-level 5 and
SELinux 30.0. Existing VINTF edits (level 6 and omitted VNDK/system-sdk blocks)
are retained as explicit unresolved integration debt, **not** evidence of ABI
compatibility. The new stock manifest advertises the same HAL instances; its
differences from the adapted manifest are only those target-level edits.
Do not describe successful XML parsing as successful VINTF or linker validation.
The legacy `extract-files.sh`/`setup-makefiles.sh` pair has not been migrated to
modern extract-utils and must not regenerate this reviewed vendor tree: it uses
the a23 vendor directory while this project uses a235f, and applies historical
VINTF edits automatically. The SEZB1 refresh used the separate audited staging
scripts, not that legacy extraction path.

Saved last_kmsg files predominantly show recovery boots (including
`First stage mount skipped (recovery mode)`), not a captured fatal Android init
failure. They do not prove that bootloader revision caused the 12-second reboot.

Required before calling the ROM usable:

1. Build the selected kernel/config on Linux, inspect final .config and compiler
   errors. Check that ext4/F2FS, dm-default-key, binder, cgroups and built-in WLAN
   are actually enabled and that Samsung enforcement options stayed disabled.
   Run `python3 device/samsung/a23/tools/check_kernel_config.py PATH_TO_GENERATED_CONFIG`
   against the generated kernel `.config` (not the input fragment). This read-only
   check rejects missing storage/encryption/Binder/cgroup features and accidentally
   retained Samsung protection options; it does not prove userspace ABI support.
2. Run full Soong/Make dependency checks, ELF/linker dependency review, SELinux
   and `checkvintf` on generated images. Legacy VNDK/FCM compatibility cannot be
   established by setting `BOARD_VNDK_VERSION := current`. Existing broad
   BUILD_BROKEN flags remain technical debt and may hide missing packages.
3. Inspect boot header, ramdisk, DTB/DTBO selection, image sizes and ZIP contents.
   Check that the updated fstab and source kernel actually reached the ZIP.
4. Test boot on SM-A235F with backups and recoverable stock firmware. Collect
   `/sys/fs/pstore/*`, `/proc/last_kmsg`, recovery.log, and live `adb logcat -b all`
   if adbd appears. Do not automatically reboot/flash while collecting evidence.
5. Test display/touch, storage/encryption, Wi-Fi/Bluetooth, calls/data/SMS,
   camera, audio/microphone, fingerprint, sensors, USB and charging/thermal.

## Server handoff

All current edits are local; the old public `main` branches do not contain them
until explicitly published. Transfer the edited device and vendor trees to the
new Linux server after syncing, or publish reviewed commits before manifest sync.
Do not start an old Crave job expecting it to pick up unpushed files.

On the designated server only, initialize `bka` with `--depth=1 --git-lfs`, use
the workspace `local_manifests/evolution-a23.xml`, and sync. Overlay these edited
trees without their `.git` directories. Do not copy the incomplete Windows
kernel checkout; sync the pinned kernel directly on Linux.

From the completed Android source root:

```bash
python3 device/samsung/a23/tools/preflight.py --root "$PWD" --server
A23_REMOTE_BUILD=1 BUILD_JOBS=12 bash device/samsung/a23/server_build.sh
```

The script saves build logs, resolved manifest and image hashes under `a23-logs`.
The remote opt-in and Windows/WSL guard prevent accidental local compilation.
No Crave job, SSH build, upload, commit, push or flash was started by this review.
Crave's retained entrypoint still uses `/opt/crave/resync.sh`; no `--clean`,
platform-directory deletion or Dev Space is introduced.

## Documentation reviewed

- https://wiki.evolution-x.org/setting-up-env
- https://wiki.evolution-x.org/en/lunch
- https://wiki.evolution-x.org/en/build_flags
- https://wiki.evolution-x.org/reporting-a-bug
- https://wiki.evolution-x.org/installing-evolution-x
- https://wiki.evolution-x.org/apply-for-maintainership
- https://wiki.evolution-x.org/en/onboarding
- https://wiki.evolution-x.org/en/automatic-building
- https://wiki.evolution-x.org/code-of-conduct
- https://wiki.evolution-x.org/en/support-new-device
- https://github.com/Evolution-X/manifest/tree/bka
- https://github.com/Evolution-X/vendor_evolution/blob/bka/config/version.mk
- https://github.com/Evolution-X/vendor_evolution/blob/bka/build/tasks/kernel.mk
- https://github.com/blxyzY/android_kernel_samsung_sm6225/tree/8c34b1fc1e921fcac33e839f7d6e9f3ea732221b

Wiki examples contain stale `bq2` references; the live manifest/version source
is authoritative. Unofficial builds use `EVO_BUILD_TYPE=Unofficial`. We retain
Google apps (`WITH_GMS=true`, requested by the user), no bundled root, and no
unverified bypass charging. GMS partition fit must be checked in the server build;
MINI/PICO variants have not been selected.
Official-maintainer CI/recovery/signing rules are distinct from this bring-up.
