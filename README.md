# Galaxy A23 4G (SM-A235F) — Evolution X `cnb` (Android 17)

Дерево с нуля, ветка `cnb-clean`. Цель: `lineage_a23-cp2a-userdebug`,
Evolution X Unofficial с GMS, загрузчик/прошивка **A235FXXSEEZB1**.

Статус: **не собрано и не проверено на телефоне.** Ниже — что сделано и почему.

## Схема

Повторяет то, что уже работает на этом телефоне (UN1CA One UI 8.5 на SEZB1):

| Раздел | Откуда |
|---|---|
| `vendor`, `odm` | **стоковые образы SEZB1 без изменений** (`vendor/samsung/a235f`, f2fs) |
| `boot` | ядро из исходников + стоковые DTB/DTBO, заголовок v2 как в стоке |
| `system`, `product` | собираются (ext4) |
| `recovery` | Lineage recovery (необязательно, можно оставить TWRP) |

Ядро — `blxyzY/android_kernel_samsung_sm6225` `master` `9eec76ce`
(исходник релиза ZestKernel 20261010, который ставит UN1CA). Оно 4.19.325, но
сообщает `bpfloader`/`netbpfload`/`netd` версию 5.10.200 (`CONFIG_FAKE_UNAME_5_10`)
и содержит бэкпорты BPF/userfaultfd. Собирается тем же clang `r563880c` и с
`KCFLAGS=-w`, как в CI автора. В ROM-ядре отключён KernelSU.

Стоковые DTB и `dtbo.img` побайтово совпадают с теми, что в рабочем
`boot.img`/`dtbo.img` релиза ядра.

## Что нужно Android 17 для vendor уровня Android 11

Проверено по исходникам android-17.0.0_r1: клиенты всех стоковых HIDL HAL
(audio 6.0, composer 2.4, gralloc 3/4, camera 2.6, radio 1.5, Wi-Fi 1.4,
health 2.1, sensors 2.0, BT 1.0, fingerprint 2.1, keymaster 4.0 через
`km_compat`) в платформе есть. Восстанавливается патчами:

| Патч | Репозиторий | Зачем |
|---|---|---|
| `patches/vndk` | `packages/modules/vndk` | APEX VNDK 30 для стоковых библиотек |
| `patches/sepolicy` | `system/sepolicy` | маппинг SELinux 30.0 (init собирает политику при загрузке) |
| `patches/vintf/0001` | `hardware/interfaces` | матрица FCM 5 |
| `patches/vintf/0002` | `kernel/configs` | требования R/4.19 для этой матрицы |
| `patches/connectivity` | `packages/modules/Connectivity` | `NetBpfLoad` без жёсткого порога ядра 5.4/5.15 (страховка к подмене uname) |
| `patches/kernel` | ядро | хостовые утилиты в окружении AOSP (`sched_param`, OpenSSL ENGINE) |

Все патчи проверены на текущий `cnb` HEAD (накладываются чисто).

## Сборка (только Linux-сервер)

1. `repo init` Evolution X `cnb`, скопировать `manifest/a23.xml` в
   `.repo/local_manifests/`, `repo sync`.
2. Из корня исходников: `bash device/samsung/a23/build_a23.sh`.

Скрипт накладывает патчи (повторный запуск безопасен), собирает стоковые
образы из частей, затем **до полной сборки** компилирует стоковую
vendor-политику SELinux так же, как это сделает init на телефоне
(`tools/check_stock_sepolicy.sh`). Ошибка там = bootloop, поэтому сборка
останавливается сразу.

`A23_BRINGUP=false` — сборка без отладочных послаблений. По умолчанию
(первые сборки) SELinux permissive и adb без подтверждения, чтобы снять
логи с первой загрузки.

Локальная проверка без исходников: `python3 device/samsung/a23/tools/preflight.py --root <корень>`.

## Прошивка

Нужны разблокированный загрузчик, TWRP и отключённый vbmeta (как для UN1CA).
OTA-zip ставится из TWRP; он записывает и стоковые vendor/odm SEZB1.
Первая установка — с форматированием data.

## Известные риски

- Не собиралось. Возможны ошибки сборки ядра/платформы на Crave.
- `android.frameworks.schedulerservice@1.0`, который требует стоковый vendor,
  в Android 17 удалён: HAL не смогут запросить RT-приоритет (не блокер).
- Аудио по Bluetooth (A2DP): у Samsung только свой HAL
  `vendor.samsung.hardware.bluetooth.audio`, AOSP-стек может его не увидеть.
- BPF-программы Android 17 на ядре с подменой 5.10 проверены только для 16 QPR2
  (UN1CA 8.5). Смотреть `logcat -b all | grep -i bpf` после первой загрузки.
