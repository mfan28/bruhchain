# ⧫ BlockchainBruhBruh

**Распределённая блокчейн-платформа с социальным профилированием.**

Каждая нода — полноценный участник сети, хранящий блоки и транзакции в общем Cassandra-кластере, файлы — в IPFS, а состояние аккаунтов — локально в LevelDB.

---

## 🏗️ Архитектура

```
┌──────────────┐
│   Майнер     │ ← HTTP API
│  (браузер)   │
└──────┬───────┘
       │ GET /mine/task → POST /mine/submit
       ▼
┌─────────────────────────────────────────┐
│            NodeManager                   │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Mempool │ │Blockchain│ │ State    │ │
│  │ (in-RAM)│ │ (logic)  │ │ (LevelDB)│ │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ │
│       │           │            │        │
│  ┌────┴───────────┴────────────┴─────┐  │
│  │          CassandraDB              │  │
│  └────────────────┬──────────────────┘  │
└───────────────────┼─────────────────────┘
                    │ gossip ring / CQL
               ┌────▼────┐  ┌────▼────┐
               │Cassandra │  │Cassandra│  ← RF=кол-во нод
               │ Node 1   │  │ Node 2  │     (динамически)
               └─────────┘  └─────────┘
┌─────────────────────────────────────────┐
│                IPFS Cluster              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │ IPFS 1   │  │ IPFS 2   │  │ IPFS 3   ││
│  │ (Москва) │  │ (СПб)    │  │ (Екб)    ││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘│
│       │             │             │       │
│  ┌────┴─────────────┴─────────────┴────┐  │
│  │        ipfs-cluster (CRDT)          │  │
│  │  файлы реплицируются по всем нодам  │  │
│  └─────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Ключевые принципы:**
- **Блоки реплицируются** через Cassandra gossip ring — не нужна ручная синхронизация
- **State Trie** (аккаунты) — локальный LevelDB на каждой ноде, переигрывается из блоков при старте и при уведомлении о новом блоке
- **Mempool** — оперативная память, не синхронизируется между нодами
- **Майнинг** — Proof-of-Work с распределёнными блокировками (Cassandra LWT, Paxos-консенсус)

---

## 🚀 Быстрый старт

### Требования
- Docker & Docker Compose
- Windows / Linux / macOS

### Запуск одной ноды

```bash
docker compose up -d
```

### Запуск второй ноды (на другой машине)

На **машине 1** (seed):
```yaml
# docker-compose.yml
services:
  cassandra:
    environment:
      CASSANDRA_SEEDS: cassandra-node
      CASSANDRA_BROADCAST_ADDRESS: 192.168.1.72   # свой IP
```

На **машине 2**:
```yaml
# docker-compose.yml — меняем container_name чтобы не было конфликта
services:
  cassandra:
    container_name: cassandra-node-2
    environment:
      CASSANDRA_SEEDS: 192.168.1.72                # IP первой машины
      CASSANDRA_BROADCAST_ADDRESS: 192.168.1.44    # свой IP
```

```bash
# На обоих машинах:
docker compose down -v   # первый раз — сброс старых данных
docker compose up -d
```

> **Важно:** `docker compose down -v` нужен только при первом подключении. После этого volumes не сбрасывать — данные сохраняются.

### Настройка IPFS Cluster для 2+ нод

IPFS работает в **приватной сети** — только ноды с одинаковым `swarm.key` видят друг друга.

**Шаг 1: Запустить первую ноду**
```bash
docker compose up -d
```

**Шаг 2: Узнать PeerID первой ноды**
```bash
docker exec ipfs-node ipfs id -f '<id>'
# → 12D3KooW...
docker exec ipfs-cluster ipfs-cluster-service id
# → 12D3KooX... (Cluster Peer ID)
```

**Шаг 3: Настроить `.env` на второй ноде**
```dotenv
CLUSTER_SECRET=c432818c79ac4e5aa122edfc9d80118f6976147c99334f79b8e4c0208f1f6efc  # тот же!
IPFS_BOOTSTRAP=/dns4/192.168.1.72/tcp/4001/p2p/12D3KooW...  # PeerID первой ноды
CLUSTER_PEER_ADDRESS=/dns4/192.168.1.72/tcp/9095/p2p/12D3KooX...  # Cluster Peer ID
```

**Шаг 4: Запустить вторую ноду**
```bash
docker compose up -d
```

Файлы, загруженные через любую ноду, автоматически реплицируются на все ноды кластера (репликация настраивается через `ipfs-cluster`).

---

## 🌐 Web UI

После запуска — открыть `http://localhost:8000`

| Вкладка | Что показывает |
|---------|----------------|
| 📊 **Overview** | Статистика сети, последние блоки, график активности |
| 💳 **Transactions** | Отправить/найти транзакцию, последние TX |
| 🧱 **Blocks** | Список блоков, просмотр по высоте/хешу |
| 👤 **Accounts** | Все аккаунты, просмотр по адресу |
| ⛏️ **Mining** | Майнинг с регулировкой сложности |
| 📦 **IPFS** | Загрузка/просмотр файлов |
| 🗄️ **Cassandra** | Просмотр таблиц Cassandra |
| 🌐 **Nodes** | Список нод в кластере |

Автообновление каждые 5 секунд.

---

## ⛏️ Майнинг

**Proof-of-Work:** SHA256 хеш должен начинаться с `difficulty` нулей.

```
pow_hash = SHA256(prev_hash + merkle_root + timestamp + difficulty + nonce + miner_address)
```

- Майнер забирает задачу через `GET /api/v1/mine/task`
- Перебирает nonce, пока не найдёт подходящий хеш
- Отправляет через `POST /api/v1/mine/submit`
- Нода проверяет PoW, применяет транзакции к State Trie, сохраняет блок в Cassandra, бродкастит пирам

**Блокировка высоты:** Перед майнингом нода захватывает эксклюзивный лок в Cassandra через LWT (`INSERT ... IF NOT EXISTS` с `ConsistencyLevel.SERIAL`). Лок живет 120 секунд. Две ноды не могут майнить одну высоту.

---

## 🗄️ Cassandra Schema

```sql
-- Blocks (все в partition=0, сортировка по height DESC)
blocks (partition int, height bigint, hash text, previous_hash text,
        merkle_root text, state_root text, difficulty int, nonce bigint,
        miner_address text, timestamp bigint, tx_count int,
        PRIMARY KEY (partition, height)) WITH CLUSTERING ORDER BY (height DESC)

-- Transactions (ключ — хеш транзакции)
transactions (hash text PRIMARY KEY, from_address text, to_address text,
              nonce bigint, payload text, signature text, timestamp bigint,
              block_height bigint, status text)

-- Индексы для быстрого поиска по блоку/адресу
transactions_by_block (block_height bigint, tx_hash text, PRIMARY KEY (block_height, tx_hash))
transactions_by_from (from_address text, timestamp bigint, tx_hash text, ...)
transactions_by_to (to_address text, timestamp bigint, tx_hash text, ...)

-- Реестр нод
nodes (node_id text PRIMARY KEY, name text, api_host text, api_port int, ...)

-- Блокировки майнинга (LWT)
mining_locks (height bigint PRIMARY KEY, node_id text, locked_at bigint)
```

Динамический **replication factor** = количество нод в кластере (минимум 2).

---

## 🧩 Структура проекта

```
blockchainbruhbruh/
├── docker-compose.yml          # Docker-оркестрация
├── README.md
├── DEVELOPERS.md               # Документация для разработчиков приложений
├── MINERS.md                   # Документация для майнеров
├── cassandra/
│   └── init-scripts/           # Инициализация Cassandra (пока пусто)
├── ipfs/
│   ├── staging/                # Staging для IPFS
│   ├── swarm.key               # Приватный ключ IPFS сети
│   └── entrypoint.sh           # Кастомный entrypoint (приватная сеть, bootstrap)
└── nodeManager/
    ├── Dockerfile
    ├── requirements.txt
    ├── config.py               # Все настройки из .env
    ├── main.py                 # FastAPI приложение, lifespan
    ├── api/
    │   ├── routes.py           # REST API эндпоинты
    │   └── p2p_routes.py       # P2P уведомления между нодами
    ├── db/
    │   └── cassandra.py        # Работа с Cassandra (CRUD, locks, node registry)
    ├── models/
    │   └── schemas.py          # Pydantic модели (Block, Transaction, MiningTask, ...)
    ├── node/
    │   ├── blockchain.py       # Логика консенсуса (создание задачи, сабмит блока)
    │   ├── mempool.py          # Пул неподтверждённых транзакций (async, thread-safe)
    │   ├── node_service.py     # Жизненный цикл ноды (регистрация, heartbeat, replay)
    │   ├── p2p_client.py       # HTTP-клиент для рассылки пирам
    │   └── state.py            # State Trie (LevelDB/plyvel)
    ├── storage/
    │   └── ipfs_client.py      # IPFS клиент (загрузка, скачивание, пиннинг)
    └── frontend/
        ├── index.html          # SPA интерфейс
        ├── js/
        │   ├── main.js         # Навигация, lazy import секций
        │   ├── helpers.js      # API-клиент, форматтеры, DOM-утилиты
        │   └── sections/       # По файлу на вкладку
        └── styles/
            ├── base.css        # Layout, sidebar, grid
            ├── components.css  # Карточки, кнопки, формы
            └── sections.css    # Специфичные стили вкладок
```

---

## 🔧 Переменные окружения

| Переменная | Дефолт | Описание |
|-----------|--------|----------|
| `CASSANDRA_HOST` | `localhost` | Адрес Cassandra |
| `CASSANDRA_PORT` | `9042` | CQL порт |
| `CASSANDRA_KEYSPACE` | `blockchain` | Имя keyspace |
| `IPFS_HOST` | `localhost` | Адрес IPFS API |
| `IPFS_PORT` | `5001` | Порт IPFS API |
| `STATE_DB_PATH` | `/data/state.db` | Путь к LevelDB |
| `MINING_DIFFICULTY` | `5` | Сложность PoW (1-20) |
| `MAX_TX_PER_BLOCK` | `100` | Макс. транзакций в блоке |
| `BLOCK_REWARD_ADDRESS` | `""` | Адрес для награды майнера |
| `HOST` | `0.0.0.0` | HTTP хост |
| `PORT` | `8000` | HTTP порт |
| `NODE_ID` | `node-{uuid}` | ID ноды |
| `NODE_HOST` | `localhost` | Внешний адрес ноды |
| `NODE_PORT` | `8000` | Внешний порт ноды |
| `SEED_PEERS` | `""` | Пиры (через запятую) |
| `CLUSTER_SECRET` | `""` | Общий секрет ipfs-cluster (32 байта hex) |
| `IPFS_BOOTSTRAP` | `""` | Bootstrap пиры IPFS (через запятую) |
| `CLUSTER_PEER_ADDRESS` | `""` | Адрес пира ipfs-cluster для подключения |

---

## 📄 Лицензия

MIT