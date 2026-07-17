#
# Copyright (C) 2024-2026 The Evolution X Project
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)

# Inherit from a23 device
$(call inherit-product, device/samsung/a23/device.mk)

# Inherit Lineage common configuration
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Device identifier
PRODUCT_NAME := lineage_a23
PRODUCT_DEVICE := a23
PRODUCT_BRAND := samsung
PRODUCT_MODEL := SM-A235F
PRODUCT_MANUFACTURER := samsung

PRODUCT_GMS_CLIENTID_BASE := android-samsung

BUILD_FINGERPRINT := samsung/a23nsxx/a23:14/UP1A.231005.007/A235FXXSBEYG1:user/release-keys

# Evolution X build flags
EVO_BUILD_TYPE := Unofficial
WITH_GMS := false
BUILD_BCR := true
TARGET_HAS_UDFPS := false
TARGET_INCLUDE_BOOT_ANIMATIONS := true
WITH_ADB_INSECURE := false
WITH_SU := false
BYPASS_CHARGE_SUPPORTED := false
TARGET_ENABLE_BLUR := true
TARGET_BOOT_ANIMATION_RES := 1080
TARGET_FACE_UNLOCK_SUPPORTED := true

# Android 16 / Baklava specifics
TARGET_SUPPORTS_64_BIT_APPS := true
