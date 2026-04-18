#!/bin/bash
# Обновляем систему и ставим зависимости
apt update && apt install -y curl wget tar

# Качаем последнюю версию панели 3x-ui напрямую из официальных релизов
# Это самая стабильная версия с поддержкой лимитов и Reality
last_version=$(curl -Ls "https://github.com" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
if [[ ! -n "$last_version" ]]; then
    last_version="v0.3.4" # Резервный вариант, если API GitHub отдаст ошибку
fi

# Сама установка ядра и панели
wget -N https://github.com{last_version}/x-ui-linux-amd64.tar.gz
cd /usr/local/ && tar zxvf /tmp/x-ui-linux-amd64.tar.gz
rm /tmp/x-ui-linux-amd64.tar.gz
cd x-ui
chmod +x x-ui bin/xray-linux-amd64
cp -f x-ui.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable x-ui
systemctl start x-ui

echo "Установка завершена! Панель доступна по порту 2053 (стандартный)."
echo "Логин/пароль по умолчанию: admin / admin"
