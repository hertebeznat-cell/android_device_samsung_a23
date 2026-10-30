#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/samsung/a23

# The device launched on Android 12 with a frozen Android 11 (API 30) vendor.
PRODUCT_SHIPPING_API_LEVEL := 31

# Dynamic partitions
PRODUCT_USE_DYNAMIC_PARTITIONS := true
PRODUCT_BUILD_SUPER_PARTITION := false

# The stock blobs link against VNDK 30 (APEX defined in Android.bp).
PRODUCT_EXTRA_VNDK_VERSIONS := 30

# SELinux: the stock vendor policy is API 30.0. Install the platform mapping
# and compat files init needs to compile it at boot (restored by
# patches/sepolicy).
PRODUCT_PACKAGES += \
    plat_30.0.cil \
    system_ext_30.0.cil \
    product_30.0.cil \
    30.0.compat.cil \
    system_ext_30.0.compat.cil

# The 4.19 kernel has userfaultfd, but not every mremap feature ART's
# concurrent-compacting GC probes for; use the default CC collector.
PRODUCT_ENABLE_UFFD_GC := false

# FCM 5 framework matrix with the R/4.19 kernel requirements (Android.bp).
PRODUCT_PACKAGES +=     framework_compatibility_matrix.5.xml

# First-stage mount
PRODUCT_COPY_FILES += \
    $(DEVICE_PATH)/rootdir/etc/fstab.default:$(TARGET_COPY_OUT_RAMDISK)/fstab.default

# Init and the Samsung Codec2 seccomp fix (see init.a23.rc)
PRODUCT_COPY_FILES +=     $(DEVICE_PATH)/rootdir/etc/init/init.a23.rc:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/init/init.a23.rc     $(DEVICE_PATH)/configs/seccomp/samsung.software.media.c2-base-policy:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/seccomp_policy/samsung.software.media.c2-base-policy

# Fingerprint: the stock HAL serves android.hardware.biometrics.fingerprint@2.1,
# but One UI declares the feature on its own system image, not in vendor.
PRODUCT_COPY_FILES +=     frameworks/native/data/etc/android.hardware.fingerprint.xml:$(TARGET_COPY_OUT_PRODUCT)/etc/permissions/android.hardware.fingerprint.xml

# Compile the always-running UI fully at build time; otherwise it runs from
# the interpreter/JIT until the first idle-maintenance dexopt.
PRODUCT_DEXPREOPT_SPEED_APPS +=     SettingsGoogle     SystemUIGoogle

# odm: stock SEZB1 files and the AOSP Bluetooth audio HAL (vendor repo), plus
# the policy and VINTF entries that make Android use it for A2DP: the stock
# audio policy has no "bluetooth" module and the stock vendor only declares
# Samsung's own Bluetooth audio HAL, so A2DP source stayed disabled and
# speakers disconnected right after pairing. audioserver reads /odm/etc first;
# the a2dp_offload_disabled name is the one it looks for when offload is off.
$(call inherit-product, vendor/samsung/a235f/a235f-vendor.mk)

PRODUCT_COPY_FILES +=     $(DEVICE_PATH)/configs/audio/audio_policy_configuration.xml:$(TARGET_COPY_OUT_ODM)/etc/audio_policy_configuration.xml     $(DEVICE_PATH)/configs/audio/audio_policy_configuration.xml:$(TARGET_COPY_OUT_ODM)/etc/audio_policy_configuration_a2dp_offload_disabled.xml     $(DEVICE_PATH)/configs/audio/audio_policy_volumes.xml:$(TARGET_COPY_OUT_ODM)/etc/audio_policy_volumes.xml     $(DEVICE_PATH)/configs/audio/bluetooth_audio_policy_configuration.xml:$(TARGET_COPY_OUT_ODM)/etc/bluetooth_audio_policy_configuration.xml     $(DEVICE_PATH)/configs/audio/default_volume_tables.xml:$(TARGET_COPY_OUT_ODM)/etc/default_volume_tables.xml     $(DEVICE_PATH)/configs/audio/r_submix_audio_policy_configuration.xml:$(TARGET_COPY_OUT_ODM)/etc/r_submix_audio_policy_configuration.xml     $(DEVICE_PATH)/configs/vintf/odm_bluetooth_audio.xml:$(TARGET_COPY_OUT_ODM)/etc/vintf/manifest/android.hardware.bluetooth.audio@2.0.xml

# Fastbootd
PRODUCT_PACKAGES += \
    fastbootd

# Overlays
PRODUCT_PACKAGES += \
    FrameworksResA23 \
    WifiResA23

# Keep Soong's graph small enough for Crave's free machines (jobs 306583 and
# 306676 were OOM-killed in "analyzing Android.bp files"). cp2a leaves
# RELEASE_ENABLE_TOT_CRONET unset, so external/cronet selects stable_* modules
# and every tot_* reference sits in an unselected select() branch; skip the
# ToT Chromium copy (~54k files) entirely.
PRODUCT_SOURCE_ROOT_DIRS += -external/cronet/tot

# Soong analyses every Android.bp in the tree. Evolution X cnb needs more than
# the 60 GB a 64 GB Crave machine allows (soong_build OOM-killed in jobs
# 308321/308326; swap is not permitted there). Leave out what this product
# never builds: vendor-side Qualcomm HALs for other SoCs (the vendor is the
# stock SEZB1 image, and no qcom-caf namespace is exported), emulators (not
# cuttlefish and goldfish: platform_testing/Android.bp lists cuttlefish tests,
# and cuttlefish imports the goldfish namespace), other form factors and
# the automotive tools built on top of them. System-side qcom code, Car and
# tests stay in.
PRODUCT_SOURCE_ROOT_DIRS += \
    -hardware/qcom-caf/msm8953 \
    -hardware/qcom-caf/msm8996 \
    -hardware/qcom-caf/sdm660 \
    -hardware/qcom-caf/sm8150 \
    -hardware/qcom-caf/sm8250 \
    -hardware/qcom-caf/sm8350 \
    -hardware/qcom-caf/sm8450 \
    -hardware/qcom-caf/sm8450-6.6 \
    -hardware/qcom-caf/sm8550 \
    -hardware/qcom-caf/sm8650 \
    -hardware/qcom-caf/sm8750 \
    -hardware/qcom-caf/sm8850 \
    -vendor/qcom/opensource/audio-hal \
    -vendor/qcom/opensource/data-ipa-cfg-mgr-legacy-um \
    -vendor/qcom/opensource/dataservices \
    -vendor/qcom/opensource/display \
    -vendor/qcom/opensource/healthd-ext \
    -vendor/qcom/opensource/libqspa \
    -vendor/qcom/opensource/libvmmem \
    -vendor/qcom/opensource/core-utils-vendor \
    -vendor/qcom/opensource/power \
    -vendor/qcom/opensource/thermal-engine \
    -vendor/qcom/opensource/usb \
    -vendor/qcom/opensource/vibrator \
    -device/generic/car \
    -device/google_car \
    -device/google/atv \
    -device/lineage/atv \
    -device/google/trout \
    -device/google/sdv \
    -device/google/sdv_display_safety \
    -device/generic/x86 \
    -device/generic/x86_64 \
    -device/sample \
    -device/qcom/sepolicy_vndr \
    -hardware/qcom/sm7250 \
    -hardware/qcom/sm8150 \
    -platform_testing/tools/automotive \
    -system/software_defined_vehicle \
    -packages/services/display_safety \
    -platform_testing/libraries/sdv \
    -platform_testing/libraries/automotive/display_safety \
    -platform_testing/tests/sdv

# cp2a turns on Soong's incremental analysis, which keeps a cache of build
# actions in memory; Crave job 308321 had soong_build OOM-killed twice at
# the 60 GB cgroup limit. One-off builds gain nothing from it.
PRODUCT_SOONG_INCREMENTAL_ANALYSIS := false

# Soong namespaces
PRODUCT_SOONG_NAMESPACES += \
    $(DEVICE_PATH)
