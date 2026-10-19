# CTS consumers of the selected stock vendor policy

Crave job 306139 reached Soong graph generation and failed because CTS
`sepolicy-cil-files` required the deliberately disabled `odm_sepolicy.cil`.
SEZB1 has no separate ODM CIL. Enabling generated ODM policy would select a
different input set from the actual stock-vendor binary.

Apply this patch to `cts`, after the `system/sepolicy` patches and before
preflight. Its two complete-file hunks are checked against the immutable AOSP
Android 17 r1 blobs recorded in `sources.json`. The existing main/recovery
policy and compatibility checks remain mandatory.

In the A23 stock mode, CTS packages a combined CIL built from the public
`precompiled_sepolicy_srcs` filegroup. This is the same complete platform,
vendor, genfs and legacy mapping input set used by the rebuilt policy.
Concatenating into one uniquely named file also avoids flattening the three
partition mapping outputs named `30.0.cil` and the two `30.0.compat.cil` files
into colliding host data names. No synthetic ODM policy is created.

Both `secilc` commands in the host test receive this same combined CIL.
`seamendc`, both `searchpolicy` comparisons and both `diff` checks are retained.
Products without the selector retain their original six separate policy
inputs. No test is disabled. This patch does not claim to resolve any future
policy compiler error.

Local regressions reconstruct tiny fixtures from the reviewed patch, check
apply/reverse behavior, reject unapplied or edited server inputs, and execute
the host script with compiler stubs. They never invoke an Android compiler:

```text
python -X utf8 -B -m unittest discover -s device/samsung/a23/tools -p test_cts_sepolicy.py
```

Official source:

- https://android.googlesource.com/platform/cts/+/refs/tags/android-17.0.0_r1/tools/selinux/Android.bp
- https://android.googlesource.com/platform/cts/+/refs/tags/android-17.0.0_r1/tools/selinux/seamendc-test.sh
