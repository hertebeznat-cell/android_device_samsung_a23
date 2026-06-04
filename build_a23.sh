#!/bin/bash
set -e

echo "⚙️ Настройка профиля Git..."
git config --global user.name "CraveBuilder"
git config --global user.email "crave@example.com"

echo "🚀 1. Инициализация репозитория Evolution X (ветка bq2)..."
repo init -u https://github.com/Evolution-X/manifest -b bq2 --depth=1 --git-lfs

echo "📝 2. Создаем local_manifest.xml..."
rm -rf .repo/local_manifests
mkdir -p .repo/local_manifests
cat << 'EOF' > .repo/local_manifests/a23.xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <project path="device/samsung/a23" name="hertebeznat-cell/android_device_samsung_a23" remote="github" revision="main" />
  <project path="vendor/samsung/a235f" name="hertebeznat-cell/android_vendor_samsung_a235f" remote="github" revision="main" />
  <project path="kernel/samsung/a23" name="hertebeznat-cell/android_kernel_samsung_a235f" remote="github" revision="main" />
</manifest>
EOF

echo "🧹 3. Жесткая очистка Git от старых косяков (решаем проблему с Clang)..."
repo forall -c 'git reset --hard HEAD && git clean -fdx' || true

echo "🗑 4. Удаление старых папок устройства и забагованного кэша компилятора..."
rm -rf device/samsung/a23 vendor/samsung/a235f kernel/samsung/a23
rm -rf prebuilts/clang/host/linux-x86

echo "🔄 5. Синхронизация исходников..."
repo sync -c -j$(nproc --all) --force-sync --no-clone-bundle --no-tags --optimized-fetch --prune

echo "🔑 5.5. Генерация приватных ключей подписи (Play Integrity)..."
rm -rf vendor/evolution-priv/keys
git clone https://github.com/Evolution-X/vendor_evolution-priv_keys-template vendor/evolution-priv/keys
cd vendor/evolution-priv/keys
./keys.sh
cd ../../../

echo "🛠 6. Настраиваем окружение и кастомные флаги..."
source build/envsetup.sh
export EVOX_BUILD_TYPE=Unofficial
export TARGET_ENABLE_BLUR=true    # Отключаем размытие для плавности
export TARGET_INCLUDE_VIPERFX=true   # Вшиваем эквалайзер ViperFX
export BUILD_BCR=true
export WITH_GMS=false # Нативная запись звонков

echo "🎯 7. Выбираем таргет (по правилам Android 15/16)..."
lunch lineage_a23-bp4a-userdebug

echo "🔥 8. Запуск компиляции..."
mka evolution -j$(nproc --all)

echo "📦 9. Поиск и загрузка готового ZIP на GoFile..."
ZIP_PATH=$(ls -S out/target/product/a23/*.zip 2>/dev/null | head -n 1)

if [ -n "$ZIP_PATH" ]; then
    echo "✅ Архив найден: $ZIP_PATH"
    echo "☁️ Устанавливаем утилиту jq для работы с API..."
    sudo apt update && sudo apt install jq -y
    
    echo "🚀 Загружаем прошивку в глобальный балансировщик GoFile..."
    RESPONSE=$(curl -s -F "file=@$ZIP_PATH" "https://upload.gofile.io/uploadfile")
    DOWNLOAD_LINK=$(echo "$RESPONSE" | jq -r '.data.downloadPage')
    
    # План Б, если балансировщик перегружен
    if [ "$DOWNLOAD_LINK" == "null" ] || [ -z "$DOWNLOAD_LINK" ]; then
        echo "⚠️ Балансировщик занят. Ищем свободный сервер вручную..."
        SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name')
        RESPONSE=$(curl -s -F "file=@$ZIP_PATH" "https://${SERVER}.gofile.io/contents/uploadfile")
        DOWNLOAD_LINK=$(echo "$RESPONSE" | jq -r '.data.downloadPage')
    fi
    
    echo "======================================================"
    echo "🎉 УРА! ПРОШИВКА ГОТОВА И ЗАГРУЖЕНА!"
    echo "👉 Твоя прямая ссылка на скачивание:"
    echo "🔗 $DOWNLOAD_LINK"
    echo "======================================================"
else
    echo "❌ ОШИБКА: ZIP-архив не найден. Сборка упала."
    exit 1
fi
