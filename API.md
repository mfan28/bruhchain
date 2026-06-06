# NodeManager — API Documentation

> **Базовый URL:** `http://<host>:<port>/api/v1` (по умолчанию `http://localhost:8000/api/v1`)

Полная спецификация REST API блокчейн-платформы **Bruhchain** (NodeManager).

---

## Содержание

- [Обзор](#обзор)
- [Модели данных](#модели-данных)
  - [Транзакция (Transaction)](#транзакция-transaction)
  - [Блок (Block)](#блок-block)
  - [Аккаунт (Account)](#аккаунт-account)
  - [Статус транзакции (TxStatus)](#статус-транзакции-txstatus)
- [Хеширование и консенсус](#хеширование-и-консенсус)
- [Эндпоинты API](#эндпоинты-api)
  - [Обзор ноды](#обзор-ноды)
  - [Транзакции](#транзакции)
  - [Блоки](#блоки)
  - [Аккаунты](#аккаунты)
  - [Майнинг](#майнинг)
  - [IPFS](#ipfs)
  - [Управление нодами](#управление-нодами)
  - [Cassandra Viewer](#cassandra-viewer)
  - [P2P (межнодовое взаимодействие)](#p2p-межнодовое-взаимодействие)
- [Коды ошибок](#коды-ошибок)
- [Ограничения](#ограничения)

---

## Обзор

NodeManager — распределённая блокчейн-платформа с социальным профилированием. Хранение данных разделено между тремя подсистемами:

| Подсистема | Хранит | Тип |
|---|---|---|
| **Cassandra** | Блоки, транзакции, регистр нод, блокировки майнинга | Распределённая NoSQL |
| **LevelDB** | Состояние аккаунтов (nonce, name, avatar, ...) | Локальная key-value БД |
| **IPFS** | Файлы (аватары, медиа) | Распределённая файловая система |

**Ключевые принципы:**
- Блоки реплицируются через Cassandra gossip ring — общая для всех нод
- Каждая нода имеет свой LevelDB (State Trie), переигрывается из блоков при старте
- Mempool — только в оперативной памяти, **не синхронизируется** между нодами
- Консенсус через Cassandra LWT (Paxos) + Proof-of-Work

---

## Модели данных

### Транзакция (Transaction)

Любое действие в системе — транзакция.

```json
{
    "hash": "abc123def456...",
    "from": "0xalice",
    "to": "0xbob",
    "nonce": 5,
    "payload": {
        "action": "state",
        "name": "Alice",
        "avatar": "Qm..."
    },
    "signature": "0x...",
    "timestamp": 1717200000,
    "status": "confirmed",
    "block_height": 42
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `hash` | string | SHA256-хеш транзакции (вычисляется нодой) |
| `from` | string | Адрес отправителя (произвольная строка) |
| `to` | string | Адрес получателя |
| `nonce` | int | Текущий nonce отправителя (защита от replay) |
| `payload` | object | Данные транзакции (см. [Actions](#actions)) |
| `signature` | string | Подпись (**не валидируется** нодой) |
| `timestamp` | int | Unix timestamp (секунды) |
| `status` | string | `pending`, `mining`, `confirmed`, `failed` |
| `block_height` | int\|null | Высота блока (null пока не подтверждена) |

#### Actions

Поле `payload.action` определяет поведение:

| action | Описание | Дополнительные поля payload |
|--------|----------|----------------------------|
| `state` | Обновляет поля аккаунта отправителя | Любые ключи (`name`, `avatar`, `description`, ...) |
| `generic` | Только увеличивает nonce | Не имеют значения |
| Любая другая строка | То же, что `generic` | Не имеют значения |

### Блок (Block)

```json
{
    "height": 42,
    "hash": "0000abcd...",
    "previous_hash": "0000ef01...",
    "merkle_root": "ffff...",
    "state_root": "aaaa...",
    "difficulty": 5,
    "nonce": 123456,
    "miner_address": "0xminer",
    "timestamp": 1717200100,
    "tx_count": 3,
    "transactions": [...]
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `height` | int | Высота блока в цепи (0 = genesis) |
| `hash` | string | SHA256-хеш заголовка блока (64 hex) |
| `previous_hash` | string | Хеш предыдущего блока |
| `merkle_root` | string | Корень дерева Меркла транзакций |
| `state_root` | string | Хеш состояния LevelDB после применения блока |
| `difficulty` | int | Сложность PoW (число ведущих нулей) |
| `nonce` | int | Nonce, найденный майнером |
| `miner_address` | string | Адрес майнера |
| `timestamp` | int | Unix timestamp блока |
| `tx_count` | int | Количество транзакций |

### Аккаунт (Account)

```json
{
    "address": "0xalice",
    "nonce": 5,
    "name": "Alice",
    "avatar": "QmAvatarCID..."
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `address` | string | Адрес аккаунта (ключ в LevelDB) |
| `nonce` | int | Счётчик транзакций (начинается с 0) |
| Прочие | any | Произвольные поля, добавленные через `action: "state"` |

### Статус транзакции (TxStatus)

| Значение | Описание |
|----------|----------|
| `pending` | В mempool, ожидает майнинга |
| `mining` | Включена в задачу майнинга |
| `confirmed` | Включена в блок, сохранена в Cassandra |
| `failed` | Отклонена (невалидный nonce) |

---

## Хеширование и консенсус

### Хеш транзакции

```
tx_hash = SHA256(from + to + nonce + payload_json + signature + timestamp)
```

`payload_json` — каноническая JSON-сериализация (`sort_keys=True`).

### Merkle Root

Бинарное дерево хешей транзакций (SHA256). При нечётном количестве — последний хеш дублируется.

### PoW хеш (для майнинга)

```
pow_hash = SHA256(previous_hash + merkle_root + timestamp + difficulty + nonce + miner_address)
```

Все параметры — строки, конкатенируются без разделителей.

**Условие:** `pow_hash` начинается с `difficulty` нулей.

### Хеш блока

```
block_hash = SHA256(previous_hash + merkle_root + timestamp + difficulty + nonce + miner_address + state_root)
```

### State Root

```
state_root = SHA256(concat(all (address + account_data) sorted by address))
```

Линейный обход LevelDB, O(n) по числу аккаунтов.

---

## Эндпоинты API

### Обзор ноды

#### `GET /api/v1/`

Информация о ноде и состоянии цепи.

**Ответ:**
```json
{
    "service": "NodeManager",
    "status": "running",
    "chain_height": 42,
    "pending_txs": 5,
    "accounts_count": 10,
    "total_txs": 150,
    "difficulty": 5,
    "miner_address": "0xreward"
}
```

---

### Транзакции

#### `POST /api/v1/transaction`

Отправить подписанную транзакцию в mempool.

**Тело запроса:**
```json
{
    "from": "0xalice",
    "to": "0xbob",
    "nonce": 0,
    "payload": {
        "action": "state",
        "name": "Alice"
    },
    "signature": "0x...",
    "timestamp": 1717200000
}
```

**Ответ (200):**
```json
{
    "hash": "abc123...",
    "status": "pending"
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 409 | Транзакция уже в mempool |

---

#### `GET /api/v1/transaction/{tx_hash}`

Получить статус транзакции.

**Параметры пути:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `tx_hash` | string | Хеш транзакции (64 hex) |

**Ответ (200):**
```json
{
    "hash": "abc123...",
    "from": "0xalice",
    "to": "0xbob",
    "nonce": 0,
    "payload": {"action": "state", "name": "Alice"},
    "signature": "0x...",
    "timestamp": 1717200000,
    "block_height": 42,
    "status": "confirmed"
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Транзакция не найдена |

---

#### `GET /api/v1/transactions/{address}`

Все транзакции адреса (отправленные + полученные).

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `address` | path | — | Адрес аккаунта |
| `limit` | query | 50 | Максимум записей |

**Ответ (200):**
```json
{
    "transactions": [
        {
            "hash": "tx1...",
            "from": "0xalice",
            "to": "0xbob",
            "nonce": 0,
            "payload": {...},
            "signature": "0x...",
            "timestamp": 1717200000,
            "block_height": 42,
            "status": "confirmed"
        }
    ],
    "count": 1
}
```

---

#### `GET /api/v1/transactions/sent/{address}`

Транзакции, **отправленные** адресом.

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `address` | path | — | Адрес отправителя |
| `limit` | query | 50 | Максимум записей |

**Формат ответа:** тот же, что `GET /transactions/{address}`.

---

#### `GET /api/v1/transactions/received/{address}`

Транзакции, **полученные** адресом.

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `address` | path | — | Адрес получателя |
| `limit` | query | 50 | Максимум записей |

**Формат ответа:** тот же, что `GET /transactions/{address}`.

---

#### `GET /api/v1/transactions/recent`

Последние подтверждённые транзакции (из последних блоков).

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `limit` | query | 20 | Максимум записей |

**Ответ (200):**
```json
{
    "transactions": [...],
    "count": 20
}
```

---

### Блоки

#### `GET /api/v1/block/latest`

Последний блок в цепи.

**Ответ (200):**
```json
{
    "height": 42,
    "hash": "0000abcd...",
    "previous_hash": "0000ef01...",
    "state_root": "aaaa...",
    "timestamp": 1717200100,
    "tx_count": 3
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Блоков ещё нет |

---

#### `GET /api/v1/blocks`

Список блоков с пагинацией (свежие сверху).

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `limit` | query | 20 | Максимум блоков |
| `offset` | query | 0 | Смещение |

**Ответ (200):**
```json
{
    "blocks": [
        {
            "height": 42,
            "hash": "0000abcd...",
            "previous_hash": "0000ef01...",
            "timestamp": 1717200100,
            "tx_count": 3,
            "miner_address": "0xminer",
            "difficulty": 5
        }
    ],
    "count": 1,
    "limit": 20,
    "offset": 0
}
```

---

#### `GET /api/v1/block/{height}`

Блок по высоте (с транзакциями).

**Параметры пути:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `height` | int | Высота блока |

**Ответ (200):**
```json
{
    "height": 42,
    "hash": "0000abcd...",
    "previous_hash": "0000ef01...",
    "merkle_root": "ffff...",
    "state_root": "aaaa...",
    "difficulty": 5,
    "nonce": 123456,
    "miner_address": "0xminer",
    "timestamp": 1717200100,
    "tx_count": 3,
    "transactions": [
        {
            "hash": "tx1...",
            "from": "0xalice",
            "to": "0xbob",
            "payload": {"action": "state", "name": "Alice"}
        }
    ]
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Блок не найден |

---

#### `GET /api/v1/block/search/hash`

Поиск блока по хешу.

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `hash` | query | Хеш блока (64 hex) |

**Формат ответа:** тот же, что `GET /block/{height}`.

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Блок не найден |

> **Примечание:** Использует `ALLOW FILTERING` — неэффективно на больших объёмах данных.

---

### Аккаунты

#### `GET /api/v1/account/{address}`

Данные аккаунта из State Trie (LevelDB).

**Параметры пути:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `address` | string | Адрес аккаунта |

**Ответ (200):**
```json
{
    "address": "0xalice",
    "nonce": 5,
    "name": "Alice",
    "avatar": "QmAvatarCID..."
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Аккаунт не найден |

---

#### `GET /api/v1/accounts`

Список всех аккаунтов (отсортированы по nonce, убывание).

**Ответ (200):**
```json
{
    "accounts": [
        {
            "address": "0xalice",
            "nonce": 5,
            "name": "Alice"
        },
        {
            "address": "0xbob",
            "nonce": 2,
            "name": "Bob"
        }
    ],
    "count": 2
}
```

---

### Майнинг

#### `GET /api/v1/mine/task`

Получить задачу для майнинга. Нода пытается эксклюзивно заблокировать следующую высоту через Cassandra LWT.

**Поведение:**
- Если транзакций нет — ждёт до 5 секунд (long-poll)
- Если высота заблокирована другой нодой — возвращает `task_id: "locked"`
- Если транзакции не появились — возвращает `task_id: "empty"`

**Ответ (200) — обычная задача:**
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "previous_hash": "0000abc123def456...",
    "merkle_root": "ffff0011...",
    "transactions": [
        {
            "hash": "tx1...",
            "from": "0xalice",
            "to": "0xbob",
            "nonce": 0,
            "payload": {"action": "state", "name": "Alice"},
            "signature": "0x...",
            "timestamp": 1717200000,
            "status": "mining"
        }
    ],
    "difficulty": 5,
    "timestamp": 1717200100,
    "reward_address": "0xreward"
}
```

**Ответ (200) — нет транзакций:**
```json
{
    "task_id": "empty",
    "previous_hash": "0000abc...",
    "merkle_root": "0000000000000000000000000000000000000000000000000000000000000000",
    "transactions": [],
    "difficulty": 5,
    "timestamp": 1717200100,
    "reward_address": "0xreward"
}
```

**Ответ (200) — высота заблокирована:**
```json
{
    "task_id": "locked",
    "previous_hash": "0000abc...",
    "merkle_root": "0000000000000000000000000000000000000000000000000000000000000000",
    "transactions": [],
    "difficulty": 5,
    "timestamp": 1717200100,
    "reward_address": "0xreward"
}
```

**Поля ответа:**
| Поле | Тип | Описание |
|------|-----|----------|
| `task_id` | string | UUID задачи (`"empty"` или `"locked"` если нет задачи) |
| `previous_hash` | string | Хеш последнего блока (64 hex) |
| `merkle_root` | string | Merkle root транзакций (64 hex) |
| `transactions` | array | Список транзакций для включения в блок |
| `difficulty` | int | Текущая сложность PoW |
| `timestamp` | int | **Единый** timestamp для майнинга и сабмита |
| `reward_address` | string | Адрес для награды |

> **Важно:** `timestamp` из задачи должен использоваться **как есть** при майнинге и сабмите. Не генерируйте новый!

---

#### `POST /api/v1/mine/submit`

Отправить найденный блок (результат PoW).

**Тело запроса:**
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "nonce": 128734,
    "miner_address": "0xminer1",
    "timestamp": 1717200100
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `task_id` | string | ID из задачи (обязательно) |
| `nonce` | int | Найденный nonce |
| `miner_address` | string | Адрес майнера |
| `timestamp` | int | **Тот же** timestamp, что был в задаче |

**Ответ (200) — успех:**
```json
{
    "success": true,
    "block_hash": "0000abcd..."
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 400 | `Unknown or expired task` — task_id невалидный или задача обработана |
| 400 | `PoW verification failed` — nonce не удовлетворяет условию difficulty |
| 400 | `Bad nonce in tx {hash} — removed from mempool` — невалидный nonce транзакции |

---

#### `GET /api/v1/mine/stats`

Статистика майнинга.

**Ответ (200):**
```json
{
    "difficulty": 5,
    "chain_height": 42,
    "total_blocks": 42,
    "miner_address": "0xreward"
}
```

---

#### `POST /api/v1/mine/difficulty`

Изменить сложность майнинга (на лету).

**Тело запроса:**
```json
{
    "difficulty": 6
}
```

| Поле | Тип | Ограничения |
|------|-----|-------------|
| `difficulty` | int | 1–20 |

**Ответ (200):**
```json
{
    "difficulty": 6
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 400 | `Difficulty must be 1-20` |

---

### IPFS

#### `POST /api/v1/ipfs/upload`

Загрузить файл в IPFS через ipfs-cluster.

**Тело запроса:** `multipart/form-data` с полем `file`.

**Ответ (200):**
```json
{
    "cid": "Qm...",
    "filename": "avatar.png",
    "size": 12345
}
```

---

#### `GET /api/v1/ipfs/{cid}`

Скачать файл из IPFS по CID.

**Параметры пути:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `cid` | string | IPFS CID файла |

**Ответ (200):** Бинарные данные файла (`Content-Type: application/octet-stream`).

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Файл не найден |

---

#### `GET /api/v1/ipfs/info/{cid}`

Метаинформация о файле в IPFS.

**Ответ (200):**
```json
{
    "Hash": "Qm...",
    "Size": 12345,
    "CumulativeSize": 12345,
    "Blocks": 1,
    "Type": "file"
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 404 | Файл не найден |

---

#### `GET /api/v1/ipfs/cluster/peers`

Список пиров ipfs-cluster.

**Ответ (200):** Массив объектов с информацией о пирах кластера.

**Ошибки:**
| Код | Причина |
|-----|---------|
| 502 | Кластер недоступен |

---

#### `GET /api/v1/ipfs/cluster/allocations`

Распределение файлов по нодам кластера.

**Ответ (200):** Массив объектов с информацией о размещении CID.

**Ошибки:**
| Код | Причина |
|-----|---------|
| 502 | Кластер недоступен |

---

#### `POST /api/v1/ipfs/cluster/recover/{cid}`

Восстановить репликацию CID в кластере.

**Ответ (200):**
```json
{
    "status": "ok",
    "cid": "Qm..."
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 502 | Ошибка кластера |

---

### Управление нодами

#### `GET /api/v1/nodes`

Список всех зарегистрированных нод.

**Ответ (200):**
```json
{
    "nodes": [
        {
            "node_id": "node-abc123",
            "name": "Node 1",
            "api_host": "192.168.1.72",
            "api_port": 8000,
            "chain_height": 42,
            "last_seen": 1717200100,
            "is_active": true,
            "is_self": true
        }
    ],
    "count": 1
}
```

---

#### `POST /api/v1/node/register`

Ручная регистрация ноды (через UI).

**Тело запроса:**
```json
{
    "node_id": "node-new",
    "name": "New Node",
    "api_host": "192.168.1.99",
    "api_port": 8000
}
```

**Ответ (200):**
```json
{
    "status": "registered",
    "node_id": "node-new"
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 400 | `node_id required` |

---

### Cassandra Viewer

> **Внимание:** Эндпoinты только для отладки. Список разрешённых таблиц ограничен.

#### `GET /api/v1/cassandra/tables`

Список таблиц в keyspace `blockchain`.

**Ответ (200):**
```json
{
    "tables": ["blocks", "transactions", "transactions_by_block",
               "transactions_by_from", "transactions_by_to",
               "nodes", "mining_locks"]
}
```

---

#### `GET /api/v1/cassandra/table/{table_name}`

Содержимое таблицы (первые N строк).

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `table_name` | path | — | Имя таблицы |
| `limit` | query | 20 | Максимум строк |

**Разрешённые таблицы:** `blocks`, `transactions`, `transactions_by_block`, `transactions_by_from`, `transactions_by_to`, `nodes`, `mining_locks`.

**Ответ (200):**
```json
{
    "table": "blocks",
    "columns": ["partition", "height", "hash", ...],
    "rows": [
        {"partition": 0, "height": 42, "hash": "0000abcd...", ...}
    ],
    "count": 1
}
```

**Ошибки:**
| Код | Причина |
|-----|---------|
| 403 | Таблица не в списке разрешённых |

---

### P2P (межнодовое взаимодействие)

> Эти эндпоинты используются нодами для синхронизации. Не предназначены для внешних клиентов.

#### `POST /api/v1/p2p/block`

Уведомление о новом блоке от другой ноды. Получатель запускает переигровку блоков из Cassandra.

**Тело запроса:**
```json
{
    "height": 43,
    "hash": "0000abcd..."
}
```

**Ответ (200):**
```json
{
    "status": "ok"
}
```

---

#### `GET /api/v1/p2p/blocks`

Получить блоки для синхронизации.

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `from_height` | query | 0 | Начиная с высоты |
| `limit` | query | 100 | Максимум блоков |

**Ответ (200):**
```json
{
    "blocks": [
        {
            "height": 0,
            "hash": "...",
            "previous_hash": "...",
            "merkle_root": "...",
            "state_root": "...",
            "difficulty": 5,
            "nonce": 0,
            "miner_address": "...",
            "timestamp": 1717200000,
            "tx_count": 1
        }
    ],
    "count": 1
}
```

---

## Коды ошибок

| HTTP код | Описание |
|----------|----------|
| 200 | Успех |
| 400 | Неверный запрос (невалидные данные, ошибка валидации) |
| 403 | Запрещено (например, неразрешённая таблица Cassandra) |
| 404 | Не найдено (транзакция, блок, аккаунт, файл) |
| 409 | Конфликт (дубликат транзакции в mempool) |
| 502 | Внешний сервис недоступен (IPFS cluster) |

---

## Ограничения

1. **Подпись не валидируется** — поле `signature` хранится как строка, нода её не проверяет
2. **Mempool не синхронизируется** — транзакция, отправленная на ноду А, не попадёт в майнинг на ноде Б. Отправляйте туда, где майните
3. **ALLOW FILTERING** — поиск блока по хешу использует `ALLOW FILTERING`, что неэффективно на больших данных
4. **State Root** — линейный обход LevelDB, O(n) по числу аккаунтов
5. **Сложность** — ограничена диапазоном 1–20
6. **Максимум транзакций в блоке** — настраивается через `MAX_TX_PER_BLOCK` (по умолчанию 100)
7. **Блокировка высоты** — TTL 120 секунд, после чего автоматически снимается
