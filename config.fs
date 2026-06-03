# Samsung Galaxy A23 fs config
# SPDX-License-Identifier: Apache-2.0

[vendor/bin/hw/android.hardware.biometrics.fingerprint@2.1-service.samsung]
mode: 0755
user: AID_SYSTEM
group: AID_SYSTEM
caps: SYS_NICE

[vendor/bin/hw/android.hardware.sensors@2.1-service.samsung-multihal]
mode: 0755
user: AID_SYSTEM
group: AID_SYSTEM
caps: NET_BIND_SERVICE
