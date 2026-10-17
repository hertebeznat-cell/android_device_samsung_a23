# Legacy VINTF requirements for the A23 Android 17 bring-up

Evolution `cnb` no longer installs FCM 5 and removed Android R kernel inputs.
SEZB1 still declares device/kernel FCM 5. Changing that declaration would not
migrate the installed stock HALs or the kernel contract.

The first patch adds the complete, nonempty FCM 5 HAL contract from
LineageOS `lineage-22.2` and installs it beside the existing Android 17/18
matrices. Its only kernel dependency is the A23's `kernel_config_r_4.19`.
The second patch restores that upstream module's four inputs, including
`minlts="4.19.110"`, unconditional and conditional kernel requirements.
No current matrix or kernel requirement is removed or weakened.

`sources.json` records upstream Git blob IDs, the exact reviewed `cnb`
Android.bp input/output, and patch SHA-256 hashes. The server helper checks
all inputs before changing either repository, preserves unrelated server
edits, and verifies every restored output. It never downloads source.

Read-only local checks:

```text
python -B device/samsung/a23/tools/test_vintf_patches.py
python -B device/samsung/a23/tools/apply_vintf_compat.py --root .
```

The guarded server pipeline applies these patches before preflight/Soong.
It retains normal `assemble_vintf`, XML schema and OTA kernel checks.
Restoring compatibility declarations does not restore framework HAL clients
that Android 17 may have removed. A full server build, generated-image
`checkvintf` and device logs remain necessary to establish compatibility.
