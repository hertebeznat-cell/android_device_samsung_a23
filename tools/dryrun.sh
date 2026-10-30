#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Dry run of crave_build.sh + build_a23.sh without an Android checkout.
#
#   bash device/samsung/a23/tools/dryrun.sh <device tree> <vendor tree> [work dir]
#   (the work dir is deleted afterwards unless DRYRUN_KEEP=1)
#
# Builds a fake Android root whose patched repositories are real git repos
# holding the exact upstream files the patches touch (fetched from the cnb /
# android-17.0.0_r1 / kernel sources), stubs repo, resync, lunch, m and secilc,
# then runs the real scripts end to end. Catches path, patch and ordering
# mistakes before a paid Crave job; it does not compile anything.
#
set -Eeuo pipefail

device_src=$(cd "$1" && pwd)
vendor_src=$(cd "$2" && pwd)
work=${3:-$(mktemp -d)}
root="$work/android"
bin="$work/bin"
rm -rf "$root" "$bin"
mkdir -p "$root/.repo" "$root/build" "$bin"

EVO=https://raw.githubusercontent.com/Evolution-X
AOSP=https://android.googlesource.com/platform
KERNEL=https://raw.githubusercontent.com/blxyzY/android_kernel_samsung_sm6225/9eec76ce9a2dbbe2707ae5f240b1c028601e78d2

fetch() {  # fetch <url> <dest>; gitiles serves base64 with ?format=TEXT
    mkdir -p "$(dirname "$2")"
    if [[ "$1" == *googlesource* ]]; then
        curl -fsSL "$1?format=TEXT" | base64 -d > "$2"
    else
        curl -fsSL "$1" -o "$2"
    fi
}

make_repo() {  # make_repo <path> [<url> <file>]...
    local path="$root/$1"
    shift
    mkdir -p "$path"
    git -C "$path" init -q
    git -C "$path" config core.autocrlf false
    while (($#)); do
        fetch "$1" "$path/$2"
        shift 2
    done
    git -C "$path" add -A
    git -C "$path" -c user.name=dryrun -c user.email=dryrun@localhost commit -qm upstream --allow-empty
}

echo "dryrun: fetching upstream files"
make_repo system/sepolicy "$EVO/system_sepolicy/cnb/compat/Android.bp" compat/Android.bp
make_repo packages/modules/Connectivity "$EVO/packages_modules_Connectivity/cnb/bpf/loader/NetBpfLoad.cpp" bpf/loader/NetBpfLoad.cpp
make_repo device/lineage/sepolicy "$EVO/device_evolution_sepolicy/cnb/common/private/genfs_contexts" common/private/genfs_contexts
make_repo kernel/samsung/a23 \
    "$KERNEL/include/uapi/linux/sched/types.h" include/uapi/linux/sched/types.h \
    "$KERNEL/scripts/sign-file.c" scripts/sign-file.c \
    "$KERNEL/scripts/extract-cert.c" scripts/extract-cert.c \
    "$KERNEL/Makefile" Makefile \
    "$KERNEL/arch/arm64/boot/dts/Makefile" arch/arm64/boot/dts/Makefile     "$KERNEL/drivers/input/touchscreen/novatek/nt36523_spi/nt36xxx.c" drivers/input/touchscreen/novatek/nt36523_spi/nt36xxx.c
# Leftover of an older project revision (job 306580): untracked Android.bp
# next to the tracked tree must be cleaned by crave_build.sh.
mkdir -p "$root/external/cronet/tot"
echo "cc_defaults { name: \"tot_cronet_cc_defaults\" }" > "$root/external/cronet/tot/Android.bp"
make_repo external/cronet
mkdir -p "$root/external/cronet/third_party/hash"
echo "cc_library { defaults: [\"cronet_aml_cc_defaults\"] }" > "$root/external/cronet/third_party/hash/Android.bp"
# A stale patch from an earlier job must be reset by crave_build.sh.
echo "stale edit from an earlier job" >> "$root/system/sepolicy/compat/Android.bp"
touch "$root/system/sepolicy/stale-untracked-file"

mkdir -p "$root/device/samsung" "$root/vendor/samsung" "$root/prebuilts/vndk/v30/arm64"
cp -r "$device_src" "$root/device/samsung/a23"
# Never take the source checkout's .git (a worktree link): the commits below
# would land in the real repository.
rm -rf "$root/device/samsung/a23/.git"
mkdir -p "$root/vendor/samsung/a235f"
cp -r "$vendor_src/BoardConfigVendor.mk" "$vendor_src/a235f-vendor.mk" "$vendor_src/tools" "$vendor_src/reference" \
      "$vendor_src/proprietary" "$vendor_src/bluetooth-audio" "$root/vendor/samsung/a235f/"
mkdir -p "$root/vendor/samsung/a235f/images"
cp "$vendor_src"/images/SHA256SUMS "$vendor_src"/images/*.xz.* "$root/vendor/samsung/a235f/images/"
for repo in device/samsung/a23 vendor/samsung/a235f; do
    git -C "$root/$repo" init -q
    git -C "$root/$repo" config core.autocrlf false
    git -C "$root/$repo" add -A
    git -C "$root/$repo" -c user.name=dryrun -c user.email=dryrun@localhost commit -qm tree
done
touch "$root/prebuilts/vndk/v30/arm64/Android.bp"
device_sha=$(git -C "$root/device/samsung/a23" rev-parse HEAD)

# --- stubs -------------------------------------------------------------------
cat > "$bin/uname" <<'EOF'
#!/bin/sh
echo Linux
EOF
cat > "$bin/repo" <<EOF
#!/bin/bash
# Stub: "repo forall [-j N] -c <cmd>" runs <cmd> in every fake project.
if [ "\$1" = forall ]; then
    while [ \$# -gt 0 ] && [ "\$1" != -c ]; do shift; done
    cmd="\$2"
    for path in \$(cd "$root" && find . -name .git -maxdepth 5 | sed 's#^\./##; s#/\.git\$##' | sort); do
        (cd "$root/\$path" && REPO_PATH="\$path" bash -c "\$cmd") || exit 1
    done
    exit 0
fi
echo "stub repo \$*"
EOF
cat > "$bin/curl" <<EOF
#!/bin/sh
# Serve this device tree's manifest instead of GitHub.
while [ \$# -gt 0 ]; do [ "\$1" = -o ] && { cp "$root/device/samsung/a23/manifest/a23.xml" "\$2"; exit 0; }; shift; done
EOF
cat > "$bin/resync.sh" <<'EOF'
#!/bin/sh
printf 'Fetching:  50%% (600/1200) platform/art\rFetching: 100%% (1200/1200)\n'
echo "repo sync has finished successfully."
EOF
# Windows ships a Store alias named python3; the server has a real one.
if ! python3 -c 'import sys' >/dev/null 2>&1; then
    printf '#!/bin/sh\nexec python "$@"\n' > "$bin/python3"
fi
chmod +x "$bin"/*

cat > "$root/build/envsetup.sh" <<'EOF'
lunch() {
    echo "stub lunch $*"
    export OUT="$PWD/out/target/product/a23" ANDROID_HOST_OUT="$PWD/out/host/linux-x86"
    mkdir -p "$ANDROID_HOST_OUT/bin"
    printf '#!/bin/sh\nout=; while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -c|-M|-f) shift;; -*) ;; *) [ -f "$1" ] || { echo "secilc stub: missing $1" >&2; exit 1; };; esac; shift; done; echo compiled > "$out"\n' > "$ANDROID_HOST_OUT/bin/secilc"
    chmod +x "$ANDROID_HOST_OUT/bin/secilc"
}
m() {
    echo "stub m $*"
    # DRYRUN_OOM=1 simulates one killed Soong run without changing the graph.
    if [ -n "${DRYRUN_OOM:-}" ] && [ ! -f "$PWD/.dryrun-killed" ]; then
        touch "$PWD/.dryrun-killed"
        echo " 1 steps failed: exit=137 # signal:killed"
        return 1
    fi
    if [ -n "${A23_LOW_MEMORY:-}${ALLOW_MISSING_DEPENDENCIES:-}" ]; then
        echo "dryrun: retry changed dependency checking" >&2
        return 1
    fi
    case " $* " in *" plat_sepolicy.cil "*)
        for f in system/etc/selinux/plat_sepolicy.cil system/etc/selinux/mapping/30.0.cil \
                 system/etc/selinux/mapping/30.0.compat.cil product/etc/selinux/product_sepolicy.cil \
                 product/etc/selinux/mapping/30.0.cil; do
            mkdir -p "$OUT/$(dirname "$f")"; echo stub > "$OUT/$f"
        done ;;
    esac
    case " $* " in *" evolution "*) touch "$OUT/EvolutionX-17.0-dryrun-a23.zip" ;; esac
    case " $* " in *" bootimage "*) touch "$OUT/boot.img" ;; esac
}
EOF

# --- run the real entry point -----------------------------------------------
crave="$work/crave_build.sh"
sed "s#/opt/crave/resync.sh#$bin/resync.sh#g" "$root/device/samsung/a23/crave_build.sh" > "$crave"
cd "$root"
PATH="$bin:$PATH" A23_DEVICE_REVISION="$device_sha" bash "$crave"

# --- results -----------------------------------------------------------------
[[ ! -e system/sepolicy/stale-untracked-file ]] || { echo "dryrun: stale file survived" >&2; exit 1; }
[[ ! -e external/cronet/third_party ]] || { echo "dryrun: stale cronet files survived" >&2; exit 1; }
[[ -f external/cronet/tot/Android.bp ]] || { echo "dryrun: tracked cronet file removed" >&2; exit 1; }
[[ -f vendor/samsung/a235f/images/vendor.img ]] || { echo "dryrun: vendor image removed" >&2; exit 1; }
for repo in system/sepolicy \
            packages/modules/Connectivity device/lineage/sepolicy kernel/samsung/a23; do
    [[ -n "$(git -C "$repo" status --porcelain)" ]] || { echo "dryrun: $repo not patched" >&2; exit 1; }
done
echo "DRYRUN=OK"
# Each run holds a full tree copy with the stock images (~1.6 GB).
if [[ -z "${DRYRUN_KEEP:-}" ]]; then
    cd /
    rm -rf -- "$work"
else
    echo "kept: $root"
fi
