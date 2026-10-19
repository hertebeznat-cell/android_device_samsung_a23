#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

# Google apps; must be set before the Lineage/Evolution configs are inherited.
WITH_GMS := true
TARGET_INCLUDE_MOSEY := false

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)

# Inherit from the device configuration.
$(call inherit-product, device/samsung/a23/device.mk)

# Inherit common Lineage/Evolution X configuration.
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

PRODUCT_NAME := lineage_a23
PRODUCT_DEVICE := a23
PRODUCT_BRAND := samsung
PRODUCT_MODEL := SM-A235F
PRODUCT_MANUFACTURER := samsung

PRODUCT_GMS_CLIENTID_BASE := android-samsung

PRODUCT_BUILD_PROP_OVERRIDES += \
    BuildDesc="a23nsxx-user 14 UP1A.231005.007 A235FXXSEEZB1 release-keys" \
    BuildFingerprint=samsung/a23nsxx/a23:14/UP1A.231005.007/A235FXXSEEZB1:user/release-keys \
    DeviceProduct=a23nsxx

# Evolution X
EVO_BUILD_TYPE := Unofficial
TARGET_BOOT_ANIMATION_RES := 1080
TARGET_HAS_UDFPS := false
TARGET_ENABLE_BLUR := false
TARGET_SUPPORTS_QUICK_TAP := false
TARGET_FACE_UNLOCK_SUPPORTED := true

# Bring-up builds: permissive SELinux and adb without authorization, so logs
# can be pulled from a first boot. Build with A23_BRINGUP=false for daily use.
ifneq ($(A23_BRINGUP),false)
WITH_ADB_INSECURE := true
endif
