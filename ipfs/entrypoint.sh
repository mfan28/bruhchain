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

# Запускаем демон
echo "🚀 Starting IPFS daemon..."
exec ipfs daemon --migrate=true