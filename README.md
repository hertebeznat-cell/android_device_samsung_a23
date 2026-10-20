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
`KCFLAGS=-w`, как в CI автора. KernelSU оставлен как в релизе: SUSFS вызывает его
функции, поэтому выключать нужно оба (`CONFIG_KSU` и `CONFIG_KSU_SUSFS`) — это не проверялось.

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
| `patches/sepolicy/0001` | `system/sepolicy` | маппинг SELinux 30.0 (init собирает политику при загрузке) |
| `patches/sepolicy/0002` | `system/sepolicy` | метки, разделённые в Android 16/17 (`proc_bpf` и др.), как Google сделал для 31.0 |
| `patches/core` | `system/core` | ueventd снова читает `/vendor/ueventd.rc` (права на /dev/kgsl, ion, DSP…) |
| `patches/vintf/0001` | `hardware/interfaces` | матрица FCM 5 |
| `patches/vintf/0002` | `kernel/configs` | требования R/4.19 для этой матрицы |
| `patches/connectivity` | `packages/modules/Connectivity` | `NetBpfLoad` без жёсткого порога ядра 5.4/5.15 (страховка к подмене uname) |
| `patches/kernel` | ядро | хостовые утилиты в окружении AOSP (`sched_param`, OpenSSL ENGINE) |

Все патчи проверены на текущий `cnb` HEAD (накладываются чисто).

Также проверено статически (без сборки):

- маппинг 30.0 не ссылается на типы, которых нет в политике cnb; стоковые
  `vendor_sepolicy.cil` и `vendor_*_contexts` используют только объявленные
  типы (кроме Samsung-приложений и `vendor_hal_atfwd_hwservice`);
- загрузчик передаёт `androidboot.fstab_suffix=default` и
  `boot_devices=soc/4804000.ufshc` (по `last_kmsg` с телефона), Android 17
  больше не читает DT-fstab;
- `linkerconfig` 17 строит VNDK-namespace по `ro.vndk.version=30`
  (из стокового `/vendor/default.prop`, который всё ещё загружается);
- цепочка `init.rc` → `init.qcom.rc` → `init.target.rc` → `init.a23.rc` цела;
- non-A/B OTA: `releasetools.py` пишет стоковые vendor/odm/dtbo, иначе
  упаковка падает на assert списка super;
- размеры super/группы, `cp2a`, `PRODUCT_EXTRA_VNDK_VERSIONS`, ресурсы оверлеев.

## Сборка на Crave

Проект **LOS 22.1** (id 93), платформа `aosp-silver`, без `--clean` и devspace.
Из локального клона `accupara/los22`:

```bash
crave run --projectID 93 --platform aosp-silver --no-patch --no-artifacts --detached --json --   "curl -fsSL https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/<sha>/crave_build.sh -o /tmp/a23.sh && A23_DEVICE_REVISION=<sha> bash /tmp/a23.sh"
```

`crave_build.sh` делает `repo init` Evolution X `cnb` с `--depth=1 --git-lfs`,
кладёт `manifest/a23.xml` в `.repo/local_manifests`, синхронизирует через
`/opt/crave/resync.sh`, сбрасывает патчи прошлых джобов в патчимых репо и
запускает `build_a23.sh`.

В логе Crave каждый этап начинается с баннера `A23 STAGE: …`, а раз в минуту
печатается `A23_PROGRESS +1h05m stage=repo-sync Fetching: 38% (431/1130)`
(при сборке — счётчик ninja `[ 46% 12400/67890 …]`). repo запускается через
`script`, чтобы рисовать прогресс без настоящего терминала. Ревизии device и
vendor закрепляются на коммитах джоба (`A23_DEVICE_REVISION`/`A23_VENDOR_REVISION`).

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

Нужны разблокированный загрузчик, TWRP и отключённый vbmeta (как для UN1CA;
boot.img собирается без AVB). OTA-zip ставится из TWRP и сам записывает
system, product, boot, dtbo и стоковые SEZB1 vendor/odm, поэтому подходит
и поверх UN1CA. Первая установка — с форматированием data.

Если не загрузится: `adb logcat -b all`, `adb shell dmesg` (adb открыт без
подтверждения), либо из TWRP `/sys/fs/pstore/console-ramoops-0`.

## Известные риски

- Не собиралось. Возможны ошибки сборки ядра/платформы на Crave.
- `android.frameworks.schedulerservice@1.0`, который требует стоковый vendor,
  в Android 17 удалён: HAL не смогут запросить RT-приоритет (не блокер).
- Аудио по Bluetooth (A2DP): у Samsung только свой HAL
  `vendor.samsung.hardware.bluetooth.audio`, AOSP-стек может его не увидеть.
- `vendor.qti.hardware.radio.atcmdfwd` (заводские AT-команды) не
  зарегистрируется: его тип есть только в политике Samsung.
- Метки точек монтирования `/efs` и др. в корне — общие (`rootfs`); для
  enforcing-сборки возможны отказы vendor_init при монтировании.
- BPF-программы Android 17 на ядре с подменой 5.10 проверены только для 16 QPR2
  (UN1CA 8.5). Смотреть `logcat -b all | grep -i bpf` после первой загрузки.
