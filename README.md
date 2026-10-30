# Galaxy A23 4G (SM-A235F) — Evolution X `cnb` (Android 17)

Актуальное дерево опубликовано в ветке `main` (ранее `cnb-clean`). Цель: `lineage_a23-cp2a-userdebug`,
Evolution X Unofficial с GMS, загрузчик/прошивка **A235FXXSEEZB1**.

Статус: **собрано (сервер, 2026-10-28, device `477a896`, vendor `49323c8`; OTA 3.2 ГБ),
на телефоне ещё не проверено.** Ниже — что сделано и почему.

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
`km_compat`) в платформе есть. Из дерева (без правки исходников Evo):

| Что | Где | Зачем |
|---|---|---|
| APEX `com.android.vndk.v30` | `Android.bp` | VNDK 30 для стоковых библиотек |
| `framework_compatibility_matrix.5.xml` + `kernel_config_r_4.19` | `Android.bp`, `configs/vintf` | матрица FCM 5 и требования R/4.19 |
| `/odm/etc/ueventd.rc` | `vendor/samsung/a235f` | права на /dev/kgsl, ion, DSP… из стокового `/vendor/ueventd.rc` |

Остаются патчами к исходникам:

| Патч | Репозиторий | Зачем |
|---|---|---|
| `patches/sepolicy/0001` | `system/sepolicy` | маппинг SELinux 30.0 (init собирает политику при загрузке) |
| `patches/sepolicy/0002` | `system/sepolicy` | метки, разделённые в Android 16/17 (`proc_bpf` и др.), как Google сделал для 31.0 |
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

Проект **LOS 22.1** (id 93), бесплатная платформа `linux16`, без `--clean` и devspace.
Из локального клона `accupara/los22`:

```bash
crave run --projectID 93 --platform linux16 --no-patch --no-artifacts --detached --json --   "curl -fsSL https://raw.githubusercontent.com/hertebeznat-cell/android_device_samsung_a23/<device-sha>/crave_build.sh -o /tmp/a23.sh && A23_DEVICE_REVISION=<device-sha> A23_VENDOR_REVISION=<vendor-sha> bash /tmp/a23.sh"
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

По умолчанию сборка с SELinux enforcing и обычным adb (с подтверждением).
`A23_BRINGUP=true` — отладочная сборка: SELinux permissive и adb без
подтверждения, чтобы снять логи с загрузки, которая не доходит до интерфейса.

Локальная проверка без исходников: `python3 device/samsung/a23/tools/preflight.py --root <корень>`.

Перед каждым запуском на Crave: `bash device/samsung/a23/tools/dryrun.sh <device> <vendor>`
— прогоняет `crave_build.sh` и `build_a23.sh` целиком на фейковом дереве с
настоящими upstream-файлами патчей и заглушками repo/lunch/m/secilc.

## Прошивка

Нужны разблокированный загрузчик, TWRP и отключённый vbmeta (как для UN1CA;
boot.img собирается без AVB). OTA-zip ставится из TWRP и сам записывает
system, product, boot, dtbo и стоковые SEZB1 vendor/odm, поэтому подходит
и поверх UN1CA. Первая установка — с форматированием data. **Перед установкой сохраните `/efs`
(IMEI, калибровка модема) из TWRP** — его OTA не трогает, но это единственная копия.

Если не загрузится: `adb logcat -b all`, `adb shell dmesg` (adb открыт без
подтверждения), либо из TWRP `/sys/fs/pstore/console-ramoops-0`.

## Память на бесплатном Crave

Бесплатные машины Crave убивали `soong_build` по памяти (джобы 306583, 306676).
`device.mk` исключает из графа Soong `external/cronet/tot` (`PRODUCT_SOURCE_ROOT_DIRS`):
`cp2a` не включает `RELEASE_ENABLE_TOT_CRONET`, сборка использует только `stable/`.
Платная `aosp-silver` проходит этот шаг и без этого.

По умолчанию `build_a23.sh` запускает не более четырёх задач одновременно
(`BUILD_JOBS` позволяет задать другое положительное число). Число видимых CPU
не отражает лимит памяти контейнера. Перед сборкой и после ошибки скрипт
печатает доступную память и доступные счётчики cgroup, включая `oom_kill`.
При `signal:killed`/`exit=137` он повторяет те же цели один раз с вдвое меньшим
числом задач. Состав исходников и проверка зависимостей при этом сохраняются.

В сборке **306988** синхронизация и проверка стоковой политики прошли,
но на 76% операций R8 для `SystemUIGoogle` получил SIGKILL. Нехватка памяти
вероятна, однако её нельзя подтвердить одним кодом 137. Старый повторный
запуск исключал `test/app_compat`, удаляя регистрацию типа `csuite_test`,
и ломал анализ ART и WM Shell. Этот режим исключения тестовых деревьев
и включение `ALLOW_MISSING_DEPENDENCIES` удалены. Это исправление ещё требует
проверки настоящей сборкой на сервере; готового OTA по этому логу нет.

Проверка повторных запусков без исходников, образов и компиляции:
`python3 tools/test_build_retry.py` из каталога device-дерева (нужен Bash).

## Известные риски

- Первая загрузка (2026-10-28, сборка `477a896`): грузится; работают модем/SIM, Wi‑Fi,
  Bluetooth, NFC, камеры, вибро, 90 Гц. Найдено и исправлено в следующей сборке:
  тач умирал после первого выключения экрана (патч ядра 0004), сервис кодеков Samsung
  падал по seccomp (`init.a23.rc`: из-за него висела запись видео и, вероятно, звук),
  не было отпечатка (feature + `config_biometric_sensors`), чёрная полоса у выреза.
- `android.frameworks.schedulerservice@1.0`, который требует стоковый vendor,
  в Android 17 удалён: HAL не смогут запросить RT-приоритет (не блокер).
- Аудио по Bluetooth (A2DP): стоковый vendor содержит только HAL Samsung
  (`ISehBluetoothAudioProvidersFactory`). В odm кладётся AOSP-шный Bluetooth
  audio HAL 2.0 (VNDK 30, см. `vendor/samsung/a235f/bluetooth-audio`), модуль
  `bluetooth` в политике аудио и манифест VINTF; аппаратная разгрузка A2DP
  выключена. odm теперь собирается (ext4) из стоковых файлов, там же
  `/odm/etc/ueventd.rc` вместо патча `system/core`.
- `vendor.qti.hardware.radio.atcmdfwd` (заводские AT-команды) не
  зарегистрируется: его тип есть только в политике Samsung.
- Точки монтирования `/carrier /spu /prism /optics` помечены типами Samsung из
  `sepolicy/private` (`/efs` — меткой AOSP). Правила стокового vendor для них
  срабатывают через атрибуты `*_30_0`; для `prism`/`optics` правил нет, в
  enforcing возможны отказы при монтировании.
- Из матрицы FCM 5 убраны HIDL HAL, которых в Android 17 нет (в т.ч.
  `memtrack@1.0`, `health.storage@1.0`, `dumpstate@1.1`): стоковые сервисы этих
  HAL фреймворк не использует.
- BPF-программы Android 17 на ядре с подменой 5.10 проверены только для 16 QPR2
  (UN1CA 8.5). Смотреть `logcat -b all | grep -i bpf` после первой загрузки.
