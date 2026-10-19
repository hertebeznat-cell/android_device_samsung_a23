#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Samsung Galaxy A23 4G (SM-A235F), Snapdragon 680 (bengal / SM6225).
#
# The SEZB1 vendor and odm partitions are shipped untouched as prebuilt
# images; only boot, system, product and recovery are built here.
#

DEVICE_PATH := device/samsung/a23

# Architecture (Kryo 265: 4x Cortex-A73 + 4x Cortex-A53). The stock vendor
# runs 32-bit HALs, so the platform keeps its 32-bit userspace.
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := cortex-a53

TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-a
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_VARIANT_RUNTIME := cortex-a53

# Bootloader / platform
TARGET_BOOTLOADER_BOARD_NAME := bengal
TARGET_BOARD_PLATFORM := bengal
TARGET_NO_BOOTLOADER := true
TARGET_NO_RADIOIMAGE := true

# OTA
AB_OTA_UPDATER := false
TARGET_OTA_ALLOW_NON_AB := true
TARGET_OTA_ASSERT_DEVICE := a23,SM-A235F
# Writes the prebuilt stock vendor/odm and dtbo images (see releasetools.py).
TARGET_RELEASETOOLS_EXTENSIONS := $(DEVICE_PATH)

# Kernel: boot image header v2, values copied from the SEZB1 boot.img.
BOARD_BOOT_HEADER_VERSION := 2
BOARD_KERNEL_BASE := 0x00000000
BOARD_KERNEL_PAGESIZE := 4096
BOARD_KERNEL_OFFSET := 0x00008000
BOARD_RAMDISK_OFFSET := 0x02000000
BOARD_KERNEL_TAGS_OFFSET := 0x01e00000
BOARD_DTB_OFFSET := 0x01f00000
BOARD_KERNEL_IMAGE_NAME := Image.gz
BOARD_KERNEL_CMDLINE := \
    console=null \
    androidboot.hardware=qcom \
    androidboot.memcg=1 \
    lpm_levels.sleep_disabled=1 \
    video=vfb:640x400,bpp=32,memsize=3072000 \
    msm_rtb.filter=0x237 \
    service_locator.enable=1 \
    androidboot.usbcontroller=4e00000.dwc3 \
    swiotlb=2048 \
    loop.max_part=7 \
    cgroup.memory=nokmem,nosocket \
    firmware_class.path=/vendor/firmware_mnt/image \
    printk.devkmsg=on

# Bring-up builds boot permissive (userdebug only); see lineage_a23.mk.
ifneq ($(A23_BRINGUP),false)
BOARD_KERNEL_CMDLINE += androidboot.selinux=permissive
endif

BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS += --kernel_offset $(BOARD_KERNEL_OFFSET)
BOARD_MKBOOTIMG_ARGS += --ramdisk_offset $(BOARD_RAMDISK_OFFSET)
BOARD_MKBOOTIMG_ARGS += --tags_offset $(BOARD_KERNEL_TAGS_OFFSET)
BOARD_MKBOOTIMG_ARGS += --dtb_offset $(BOARD_DTB_OFFSET)

# Stock SEZB1 DTB and DTBO: byte-identical to the ones used by the working
# ZestKernel/UN1CA releases for this device.
BOARD_INCLUDE_DTB_IN_BOOTIMG := true
BOARD_PREBUILT_DTBIMAGE_DIR := $(DEVICE_PATH)/prebuilt/dtb
BOARD_PREBUILT_DTBOIMAGE := $(DEVICE_PATH)/prebuilt/dtbo.img
BOARD_INCLUDE_RECOVERY_DTBO := true

# The Samsung TEE binds keys to the boot patch level; keep the SEZB1 value.
BOOT_SECURITY_PATCH := 2026-02-05

# blxyzY SM6225 kernel (4.19.325-cip): reports 5.10 to the BPF loaders and
# carries the BPF/userfaultfd backports Android 16+ needs.
TARGET_KERNEL_SOURCE := kernel/samsung/a23
TARGET_KERNEL_CONFIG := a23_eur_open_defconfig
TARGET_KERNEL_CONFIG_EXT := $(DEVICE_PATH)/configs/kernel/a23_evo.config
KERNEL_LTO := thin
# Same clang as the upstream CI release (NDK r29, clang-r563880c).
TARGET_KERNEL_CLANG_VERSION := r563880c
# Same make flags as the upstream build.sh (Evolution adds LLVM=1 LLVM_IAS=1):
# this 4.19 tree derives clang's --target from CROSS_COMPILE, and new-clang
# warnings are silenced with KCFLAGS=-w.
# Evolution always runs "make dtbs" when the tree has DTS sources; build them
# with the kernel's own overlay-capable dtc, as upstream does. The resulting
# DTBs are not used: boot.img carries the stock ones.
TARGET_KERNEL_ADDITIONAL_FLAGS := \
    CROSS_COMPILE=aarch64-linux-gnu- \
    KCFLAGS=-w \
    DTC_EXT=$(abspath $(TARGET_KERNEL_SOURCE))/tools/dtc \
    CONFIG_BUILD_ARM64_DT_OVERLAY=y

# Partitions
BOARD_FLASH_BLOCK_SIZE := 262144
BOARD_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 100663296
BOARD_DTBOIMG_PARTITION_SIZE := 8388608
BOARD_CACHEIMAGE_PARTITION_SIZE := 209715200
BOARD_CACHEIMAGE_FILE_SYSTEM_TYPE := ext4

# Dynamic partitions: the layout of the SEZB1 super image.
BOARD_SUPER_PARTITION_SIZE := 9017753600
BOARD_SUPER_PARTITION_GROUPS := qti_dynamic_partitions
BOARD_QTI_DYNAMIC_PARTITIONS_SIZE := 9013559296
BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST := system product vendor odm

BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true

# Mount points used by the stock vendor fstab. Samsung's own system image
# creates them; the AOSP root does not. /efs holds the modem calibration/IMEI
# and /metadata the userdata encryption keys.
BOARD_USES_METADATA_PARTITION := true
BOARD_ROOT_EXTRA_FOLDERS := carrier efs optics prism spu

TARGET_COPY_OUT_PRODUCT := product
TARGET_COPY_OUT_VENDOR := vendor
TARGET_COPY_OUT_ODM := odm

# Stock vendor/odm (f2fs) images, assembled by vendor/samsung/a235f.
include vendor/samsung/a235f/BoardConfigVendor.mk

# Verified boot is not used: the device runs with a disabled vbmeta and the
# stock vendor/odm images carry Samsung's own footers.
BOARD_AVB_ENABLE := false

# Recovery
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/rootdir/etc/fstab.default
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
BOARD_HAS_DOWNLOAD_MODE := true

# Properties
TARGET_PRODUCT_PROP += $(DEVICE_PATH)/product.prop

# Display
TARGET_SCREEN_DENSITY := 450
