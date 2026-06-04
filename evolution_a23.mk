#
# Copyright (C) 2024-2026 The Evolution X Project
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)

# Inherit from a23 device
$(call inherit-product, device/samsung/a23/device.mk)

# Inherit Evolution X common configuration
$(call inherit-product, vendor/evolution/config/common_full_phone.mk)

# Device identifier
PRODUCT_NAME := evolution_a23
PRODUCT_DEVICE := a23
PRODUCT_BRAND := samsung
PRODUCT_MODEL := SM-A235F
PRODUCT_MANUFACTURER := samsung

PRODUCT_GMS_CLIENTID_BASE := android-samsung

PRODUCT_BUILD_PROP_OVERRIDES += \
    PRIVATE_BUILD_DESC="a23nsxx-user 14 UP1A.231005.007 A235FXXSBDXD1 release-keys"

BUILD_FINGERPRINT := samsung/a23nsxx/a23:14/UP1A.231005.007/A235FXXSBDXD1:user/release-keys

# Evolution X specific flags
EVOLUTION_BUILD_TYPE := UNOFFICIAL
EVO_BUILD_TYPE := UNOFFICIAL
TARGET_BOOT_ANIMATION_RES := 1080
TARGET_FACE_UNLOCK_SUPPORTED := true

# Android 16 / Baklava specifics
TARGET_SUPPORTS_64_BIT_APPS := true
