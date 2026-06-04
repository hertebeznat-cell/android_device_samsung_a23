#!/bin/bash
set -e

echo "⚙️ Настройка профиля Git..."
git config --global user.name "CraveBuilder"
git config --global user.email "crave@example.com"

echo "1. Инициализация репозитория Evolution X (ветка bq2)..."
repo init -u https://github.com/Evolution-X/manifest -b bq2 --depth=1 --git-lfs

echo "📝 2. Создаем правильный local_manifest.xml..."
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

echo "🧹 3. Жесткая очистка Git от старых косяков и мусора..."
repo forall -c 'git reset --hard HEAD && git clean -fdx' || true

echo "🗑 4. Удаление старых папок устройства для чистого синка..."
rm -rf device/samsung/a23
rm -rf vendor/samsung/a235f
rm -rf kernel/samsung/a23

echo "🔄 5. Синхронизация исходников (repo sync)..."
repo sync -c -j$(nproc --all) --force-sync --no-clone-bundle --no-tags --optimized-fetch --prune

echo "🛠 6. Настраиваем окружение сборки..."
source build/envsetup.sh
export EVOX_BUILD_TYPE=Unofficial

echo "🎯 7. Выбираем таргет сборки (lunch)..."
lunch evolution_a23-userdebug

echo "🔥 8. Запуск компиляции прошивки..."
mka evolution -j$(nproc --all)

echo "📦 9. Сборка завершена! Ищем готовый ZIP-архив..."
# Находим самый большой zip-файл в папке устройства
ZIP_PATH=$(ls -S out/target/product/a23/*.zip 2>/dev/null | head -n 1)

if [ -n "$ZIP_PATH" ]; then
    echo "✅ Архив найден: $ZIP_PATH"
    echo "☁️ Устанавливаем jq и запрашиваем свободный сервер GoFile..."
    
    sudo apt update && sudo apt install jq -y
    
    # Шаг 1: Узнаем у API GoFile, какой сервер сейчас готов принять файл
    SERVER=$(curl -s https://api.gofile.io/getServer | jq -r '.data.server')
    
    # Резервный вариант проверки сервера на случай изменения API
    if [ -z "$SERVER" ] || [ "$SERVER" == "null" ]; then
        SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name')
    fi
    
    echo "🚀 Используем сервер: $SERVER. Начинаем загрузку прошивки..."
    
    # Шаг 2: Пушим сам файл на распределенный сервер и вытаскиваем ссылку
    RESPONSE=$(curl -F "file=@$ZIP_PATH" "https://${SERVER}.gofile.io/uploadFile")
    DOWNLOAD_LINK=$(echo "$RESPONSE" | jq -r '.data.downloadPage')
    
    echo "======================================================"
    echo "🎉 УРА! Прошивка успешно скомпилирована и загружена!"
    echo "👉 Скачать твой билд Evolution X можно тут:"
    echo "🔗 $DOWNLOAD_LINK"
    echo "======================================================"
else
    echo "❌ ОШИБКА: ZIP-архив не найден. Сборка упала, чекни логи выше."
    exit 1
fi
