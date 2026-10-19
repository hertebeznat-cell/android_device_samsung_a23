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

# The stock blobs link against VNDK 30 (restored by patches/vndk).
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

# First-stage mount
PRODUCT_COPY_FILES += \
    $(DEVICE_PATH)/rootdir/etc/fstab.default:$(TARGET_COPY_OUT_RAMDISK)/fstab.default

# Fastbootd
PRODUCT_PACKAGES += \
    fastbootd

# Overlays
PRODUCT_PACKAGES += \
    FrameworksResA23 \
    WifiResA23

# Soong namespaces
PRODUCT_SOONG_NAMESPACES += \
    $(DEVICE_PATH)
