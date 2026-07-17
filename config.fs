# Samsung Galaxy A23 fs config
# SPDX-License-Identifier: Apache-2.0

[AID_VENDOR_QTI_DIAG]
value: 2901

[AID_VENDOR_RFS_SHARED]
value: 2904

[AID_VENDOR_QRTR]
value: 2906

[AID_VENDOR_SECDIR]
value: 5050

[AID_VENDOR_SPAY]
value: 5279

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
