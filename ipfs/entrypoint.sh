#!/bin/sh
set -e

export IPFS_PATH="/data/ipfs"

# Инициализация если первый запуск
if [ ! -f "$IPFS_PATH/config" ]; then
    echo "📦 Initializing IPFS..."
    ipfs init --profile=server
fi

# Устанавливаем swarm.key для приватной сети
if [ -f /swarm/swarm.key ]; then
    mkdir -p "$IPFS_PATH"
    cp /swarm/swarm.key "$IPFS_PATH/swarm.key"
    echo "🔐 Private swarm key installed"
fi

# Отключаем публичные bootstrap ноды
ipfs bootstrap rm --all 2>/dev/null || true
echo "🗑️ Public bootstraps removed"

# Добавляем свои bootstrap пиры
if [ -n "$IPFS_BOOTSTRAP" ]; then
    echo "$IPFS_BOOTSTRAP" | tr ',' '\n' | while IFS= read -r peer; do
        [ -n "$peer" ] && ipfs bootstrap add "$peer" && echo "➕ Bootstrap: $peer"
    done
fi

# Отключаем публичную DHT — только приватная сеть
ipfs config --json Routing.Type '"none"' 2>/dev/null || true

# Отключаем AutoConf (он лезет в публичный интернет)
ipfs config --json AutoConf.Enabled false 2>/dev/null || true

# API и Gateway должны слушать на всех интерфейсах, не только localhost
echo "🔧 Setting API to 0.0.0.0:5001..."
ipfs config Addresses.API "/ip4/0.0.0.0/tcp/5001"
echo "🔧 Setting Gateway to 0.0.0.0:8080..."
ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/8080"

# Запускаем демон
echo "🚀 Starting IPFS daemon..."
exec ipfs daemon --migrate=true