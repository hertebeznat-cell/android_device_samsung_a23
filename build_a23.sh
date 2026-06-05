#!/bin/bash
set -e

echo "⚙️ Настройка Git..."
git config --global user.name "CraveBuilder"
git config --global user.email "crave@example.com"

echo "🚀 1. Инициализация Evolution X..."
repo init -u https://github.com/Evolution-X/manifest -b bq2 --depth=1 --no-clone-bundle

echo "📝 2. Создаем local_manifest.xml..."
mkdir -p .repo/local_manifests
cat << 'EOF' > .repo/local_manifests/a23.xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <project path="device/samsung/a23" name="hertebeznat-cell/android_device_samsung_a23" remote="github" revision="main" />
  <project path="vendor/samsung/a235f" name="hertebeznat-cell/android_vendor_samsung_a235f" remote="github" revision="main" />
  <project path="kernel/samsung/a23" name="hertebeznat-cell/android_kernel_samsung_a235f" remote="github" revision="main" />
</manifest>
EOF

echo "🔪 3. Вырезаем GMS из манифеста, чтобы избежать 502 ошибки..."
# Удаляем ссылку на gms из манифеста, если она там есть
sed -i '/vendor\/gms/d' .repo/manifests/default.xml || true

echo "🔄 4. Синхронизация (без GMS)..."
repo sync -c -j$(nproc --all) --force-sync --no-tags --optimized-fetch

echo "🛠 5. Настройка окружения..."
source build/envsetup.sh
export EVOX_BUILD_TYPE=Unofficial
export WITH_GMS=false
export TARGET_ENABLE_BLUR=false

echo "🎯 6. Выбираем таргет..."
lunch lineage_a23-userdebug

echo "🔥 7. Запуск компиляции..."
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
