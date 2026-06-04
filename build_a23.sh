#!/bin/bash
set -e

echo "⚙️ Настройка Git..."
git config --global user.name "CraveBuilder"
git config --global user.email "crave@example.com"

echo "🚀 Инициализация исходников Evolution X (ветка bq2)..."
repo init -u https://github.com/Evolution-X/manifest -b bq2 --depth=1 --git-lfs

echo "📝 Создаем local_manifest.xml..."
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

echo "🔄 Синхронизируем репозитории..."
repo sync -c -j$(nproc --all) --force-sync --no-clone-bundle --no-tags --optimized-fetch --prune

echo "🛠 Настраиваем окружение сборки..."
source build/envsetup.sh
export EVOX_BUILD_TYPE=Unofficial

echo "🎯 Выбираем таргет (lunch)..."
lunch evolution_a23-userdebug

echo "🔥 Запускаем компиляцию..."
mka evolution -j$(nproc --all)

echo "📦 Сборка завершена! Ищем готовый ZIP-архив..."
# Ищем ВСЕ zip-файлы в папке a23 и берем самый большой по размеру
ZIP_PATH=$(ls -S out/target/product/a23/*.zip 2>/dev/null | head -n 1)

if [ -n "$ZIP_PATH" ]; then
    echo "✅ Архив найден! Устанавливаем GitHub CLI..."
    echo "Файл: $ZIP_PATH"
    
    sudo apt update && sudo apt install gh -y
    
    echo "🔑 Авторизуемся на GitHub..."
    # ВНИМАНИЕ: ВСТАВЬ СЮДА СВОЙ ТОКЕН НА 7 ДНЕЙ
    export GITHUB_TOKEN="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" 
    
    # Генерируем имя релиза (например, build-202606041230)
    TAG_NAME="build-$(date +%Y%m%d%H%M)"
    
    echo "☁️ Загружаем прошивку в релизы приватного репозитория..."
    # ВНИМАНИЕ: ЗАМЕНИ "ТВОЙ_ЛОГИН/ТВОЙ_РЕПОЗИТОРИЙ" НА СВОИ ДАННЫЕ
    gh release create "$TAG_NAME" "$ZIP_PATH" --repo hertebeznat-cell/A23-Builds --title "EvoX A23 - $TAG_NAME" --notes "Автоматическая сборка Crave"
    
    echo "🎉 ГОТОВО! Прошивка загружена в твой приватный репозиторий в раздел Releases!"
else
    echo "❌ ОШИБКА: ZIP-архив не найден. Похоже, сборка упала."
    exit 1
fi
