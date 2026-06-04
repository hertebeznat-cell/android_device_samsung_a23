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
# Эта команда сбрасывает локальные изменения абсолютно во ВСЕХ репозиториях базы (включая clang)
repo forall -c 'git reset --hard HEAD && git clean -fdx' || true

echo "🗑 4. Удаление старых папок устройства для чистого синка..."
# Принудительно сносим старые папки а23, чтобы repo sync выкачал их с твоего Гита с нуля
rm -rf device/samsung/a23
rm -rf vendor/samsung/a235f
rm -rf kernel/samsung/a23

echo "🔄 5. Синхронизация исходников (repo sync)..."
repo sync -c -j$(nproc --all) --force-sync --no-clone-bundle --no-tags --optimized-fetch --prune

echo "🛠 6. Настраиваем окружение сборки..."
source build/envsetup.sh
export EVOX_BUILD_TYPE=Unofficial

echo "🎯 7. Выбираем тагер сборки (lunch)..."
lunch evolution_a23-userdebug

echo "🔥 8. Запуск компиляции прошивки..."
mka evolution -j$(nproc --all)

echo "📦 9. Сборка завершена! Ищем готовый ZIP-архив..."
# Ищем самый большой zip-файл в папке устройства
ZIP_PATH=$(ls -S out/target/product/a23/*.zip 2>/dev/null | head -n 1)

if [ -n "$ZIP_PATH" ]; then
    echo "✅ Архив найден: $ZIP_PATH"
    echo "☁️ Устанавливаем GitHub CLI и заливаем в Releases..."
    
    sudo apt update && sudo apt install gh -y
    
    echo "🔑 Авторизация на GitHub..."
    # ВСТАВЬ СЮДА СВОЙ ТОКЕН НА 7 ДНЕЙ
    export GITHUB_TOKEN="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" 
    
    TAG_NAME="build-$(date +%Y%m%d%H%M)"
    
    echo "🚀 Отправка файла в приватный репозиторий..."
    # ЗАМЕНИ НА СВОЙ ЛОГИН И НАЗВАНИЕ ПРИВАТНОГО РЕПО-ХРАНИЛИЩА
    gh release create "$TAG_NAME" "$ZIP_PATH" --repo hertebeznat-cell/A23-Builds --title "EvoX A23 - $TAG_NAME" --notes "Автоматическая сборка через Crave CI/CD"
    
    echo "🎉 ИДЕАЛЬНО! Прошивка лежит в твоих релизах на GitHub!"
else
    echo "❌ ОШИБКА: ZIP-архив не найден. Сборка упала, чекни логи выше."
    exit 1
fi
