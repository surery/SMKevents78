#!/bin/bash

set -e

echo "[1/6] Обновление системы..."
apt update && apt upgrade -y

echo "[2/6] Установка зависимостей..."
apt install -y curl wget git ufw

echo "[3/6] Установка WireGuard..."
apt install -y wireguard

echo "[4/6] Настройка сети..."
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p

echo "[5/6] Генерация ключей..."
mkdir -p /etc/wireguard
cd /etc/wireguard

wg genkey | tee server_private.key | wg pubkey > server_public.key

SERVER_PRIV=$(cat server_private.key)

cat > wg0.conf <<EOF
[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIV
SaveConfig = true

PostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
EOF

echo "[6/6] Запуск WireGuard..."
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

echo "Готово."
