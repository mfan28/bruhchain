#!/bin/sh
set -e

# Инициализация репозитория при первом запуске
if [ ! -f /data/ipfs/config ]; then
    echo "Initializing IPFS repository..."
    ipfs init --profile=server

    # Отключаем AutoConf
    ipfs config --json AutoConf.Enabled false

    # Убираем всё auto из конфигурации
    ipfs bootstrap rm --all
    ipfs config --json DNS.Resolvers '{}'
    ipfs config Routing.Type none

    ipfs config Addresses.API /ip4/0.0.0.0/tcp/5001
    ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8080
    ipfs config --json Addresses.Announce '["/ip4/192.168.1.72/tcp/4001"]'
    ipfs config --json Addresses.Swarm '["/ip4/0.0.0.0/tcp/4001", "/ip6/::/tcp/4001", "/ip4/0.0.0.0/udp/4001/quic-v1", "/ip4/0.0.0.0/udp/4001/quic-v1/webtransport", "/ip6/::/udp/4001/quic-v1", "/ip6/::/udp/4001/quic-v1/webtransport"]'

fi

# Запускаем демон
exec ipfs daemon